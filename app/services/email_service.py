"""
Email Service Module

Email service using Amazon SES.
Creates HTML emails using Jinja2 template engine.
"""

import logging
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import boto3
from botocore.exceptions import ClientError
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.config import settings
from app.models.draw import Draw, DrawResult, Participant, Language
from app.core.security import create_participant_token, create_unsubscribe_token
from app.utils.names import draw_display_name

logger = logging.getLogger(__name__)


class EmailService:
    """Email service using Amazon SES"""
    
    # Template configuration
    TEMPLATE_CONFIG = {
        Language.EN.value: {
            'template': 'email-template-en.html',
            'subject': '🎁 Santa drew a name for you!'
        },
        Language.TR.value: {
            'template': 'email-template-tr.html',
            'subject': '🎁 Noel Baba senin için bir isim çekti!'
        },
        'reset_password_en': {
            'template': 'reset-password-template-en.html',
            'subject': '🔑 Reset your Let\'s Raffle password'
        },
        'reset_password_tr': {
            'template': 'reset-password-template-tr.html',
            'subject': '🔑 Let\'s Raffle şifre sıfırlama'
        }
    }
    
    # E-mails around a draw other than the result: one bilingual template each
    DRAW_EMAIL_CONFIG = {
        'join_confirmation': {
            'template': 'join-confirmation.html',
            'subject': {'TR': '🎄 Çekilişe katıldın: {name}', 'EN': "🎄 You're in: {name}"},
        },
        'draw_created': {
            'template': 'draw-created.html',
            'subject': {'TR': '🎁 Çekilişin hazır: {name}', 'EN': '🎁 Your draw is ready: {name}'},
        },
        'draw_not_run': {
            'template': 'draw-not-run.html',
            'subject': {'TR': '⏳ Çekiliş yapılamadı: {name}', 'EN': "⏳ Your draw couldn't run: {name}"},
        },
        'draw_reminder': {
            'template': 'draw-reminder.html',
            'subject': {'TR': '⏰ Çekilişin yarın: {name}', 'EN': '⏰ Your draw is tomorrow: {name}'},
        },
    }

    MONTHS = {
        'TR': ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'],
        'EN': ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    }

    # Announcement campaigns sent with scripts/send_announcement.py
    ANNOUNCEMENT_CONFIG = {
        '2027-launch': {
            Language.TR.value: {
                'template': 'announcement-2027-tr.html',
                'subject': '🎄 Lets Raffle 2027: yeni tasarım, iPhone uygulaması ve dahası',
                'text': (
                    "Lets Raffle 2027 için baştan aşağı yenilendi: yeni tasarım, iPhone uygulaması, "
                    "ofise asmalık QR kodlu afiş ve hikâyede paylaşılabilen davetiye.\n\n"
                    "Çekilişini başlat: {site}\n"
                    "iPhone uygulaması: {app_store}\n\n"
                    "Bu e-postaları almak istemiyorsan listeden çık: {unsubscribe}\n"
                ),
            },
            Language.EN.value: {
                'template': 'announcement-2027-en.html',
                'subject': '🎄 Lets Raffle 2027: a new look, an iPhone app and more',
                'text': (
                    "Lets Raffle has been rebuilt for 2027: a new look, an iPhone app, "
                    "a printable QR poster for the office and an invitation card for stories.\n\n"
                    "Start your draw: {site}\n"
                    "iPhone app: {app_store}\n\n"
                    "To stop receiving these e-mails, unsubscribe: {unsubscribe}\n"
                ),
            },
        },
    }

    def __init__(self):
        """Initialize SES client and Jinja2 environment"""
        self.ses_client = self._create_ses_client()
        self.from_email = settings.ses_from_email
        self.jinja_env = self._create_jinja_env()
    
    def _create_ses_client(self) -> boto3.client:
        """Create and configure SES client"""
        ses_config = {}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            ses_config = {
                'aws_access_key_id': settings.aws_access_key_id,
                'aws_secret_access_key': settings.aws_secret_access_key
            }
        
        return boto3.client(
            'ses',
            region_name=settings.aws_region,
            **ses_config
        )
    
    def _create_jinja_env(self) -> Environment:
        """Create and configure Jinja2 environment"""
        template_dir = Path(__file__).parent.parent / 'templates'
        return Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )
    
    def _get_template_config(self, language: str) -> Dict[str, str]:
        """Get template configuration for given language"""
        return self.TEMPLATE_CONFIG.get(
            language,
            self.TEMPLATE_CONFIG[Language.TR.value]  # Default to Turkish
        )
    
    @staticmethod
    def reveal_link(giver: Participant, draw: Draw) -> str:
        """Personal link to the web page that reveals the giver's match (no match details in the email)."""
        token = create_participant_token(giver.id, draw.id)
        return f"{settings.frontend_url.rstrip('/')}/reveal/{token}"

    def _build_template_context(
        self,
        giver: Participant,
        draw: Draw,
    ) -> Dict[str, str]:
        """Build template context for the draw result email.

        The receiver is intentionally not included: the email only links to the reveal page.
        """
        return {
            'lang': (draw.language or Language.TR.value).lower(),
            'asset_base': settings.frontend_url.rstrip('/'),
            'participant_name': giver.first_name,
            'reveal_link': self.reveal_link(giver, draw),
        }

    def send_draw_result_email(
        self,
        draw: Draw,
        giver: Participant,
        receiver: Participant
    ) -> bool:
        """
        Send draw result email to participant (single email)
        
        Args:
            draw: Draw object
            giver: Participant who gives the gift
            receiver: Participant who receives the gift
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            config = self._get_template_config(draw.language)
            template = self.jinja_env.get_template(config['template'])
            context = self._build_template_context(giver, draw)
            body_html = template.render(**context)
            
            response = self.ses_client.send_email(
                Source=self.from_email,
                Destination={'ToAddresses': [giver.email]},
                Message={
                    'Subject': {'Data': config['subject'], 'Charset': 'UTF-8'},
                    'Body': {'Html': {'Data': body_html, 'Charset': 'UTF-8'}}
                }
            )
            logger.info(
                f"Email sent successfully to {giver.email} for draw {draw.id}. "
                f"MessageId: {response['MessageId']}"
            )
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(
                f"Failed to send email to {giver.email} for draw {draw.id}: "
                f"{error_code} - {error_message}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error sending email to {giver.email} for draw {draw.id}: {e}",
                exc_info=True
            )
            return False
    
    def send_draw_results_to_all_participants(
        self,
        draw: Draw,
        draw_results: List[DrawResult],
        participants_dict: Dict[int, Participant]
    ) -> Dict[str, bool]:
        """
        Send emails to all participants with their draw results
        
        Each participant receives information about who they will give a gift to.
        HTML template is read and relevant fields are filled.
        
        Args:
            draw: Draw object
            draw_results: List of DrawResult objects
            participants_dict: Dictionary mapping participant_id to Participant object
            
        Returns:
            Dictionary mapping email to success status
        """
        results = {}
        
        for draw_result in draw_results:
            giver = participants_dict.get(draw_result.giver_participant_id)
            receiver = participants_dict.get(draw_result.receiver_participant_id)
            
            if not self._validate_participants(draw_result, giver, receiver):
                continue
            
            success = self.send_draw_result_email(
                draw=draw,
                giver=giver,
                receiver=receiver
            )
            results[giver.email] = success
        
        self._log_email_summary(draw.id, results)
        return results
    
    def _validate_participants(
        self,
        draw_result: DrawResult,
        giver: Participant,
        receiver: Participant
    ) -> bool:
        """Validate that both giver and receiver participants exist"""
        if not giver:
            logger.warning(
                f"Giver participant not found for draw_result {draw_result.id}, "
                f"giver_participant_id={draw_result.giver_participant_id}"
            )
            return False
        
        if not receiver:
            logger.warning(
                f"Receiver participant not found for draw_result {draw_result.id}, "
                f"receiver_participant_id={draw_result.receiver_participant_id}"
            )
            return False
        
        return True
    
    def _log_email_summary(self, draw_id: int, results: Dict[str, bool]) -> None:
        """Log summary of email sending results"""
        successful_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        logger.info(
            f"Email sending completed for draw {draw_id}: "
            f"{successful_count}/{total_count} emails sent successfully"
        )

    def send_password_reset_email(self, email: str, token: str, language: str = Language.TR.value) -> bool:
        """
        Send password reset email to user
        
        Args:
            email: User's email address
            token: Reset token
            language: Language code (default: tr)
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Determine config based on language (case-insensitive)
            lang_upper = language.upper()
            config_key = 'reset_password_tr' if lang_upper == 'TR' else 'reset_password_en'
            config = self.TEMPLATE_CONFIG.get(config_key, self.TEMPLATE_CONFIG['reset_password_tr'])
            
            template = self.jinja_env.get_template(config['template'])
            
            # Create reset link
            reset_link = f"{settings.frontend_url}/reset-password?token={token}"
            
            context = {
                'lang': 'tr' if lang_upper == 'TR' else 'en',
                'asset_base': settings.frontend_url.rstrip('/'),
                'reset_link': reset_link,
            }
            
            body_html = template.render(**context)
            
            response = self.ses_client.send_email(
                Source=self.from_email,
                Destination={'ToAddresses': [email]},
                Message={
                    'Subject': {'Data': config['subject'], 'Charset': 'UTF-8'},
                    'Body': {'Html': {'Data': body_html, 'Charset': 'UTF-8'}}
                }
            )
            
            logger.info(f"Password reset email sent to {email}. MessageId: {response['MessageId']}")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"Failed to send password reset email to {email}: {error_code} - {error_message}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending password reset email to {email}: {e}", exc_info=True)
            return False


    @staticmethod
    def unsubscribe_link(email: str, language: str = Language.TR.value) -> str:
        """Personal opt-out link for announcement e-mails (served by this API)."""
        token = create_unsubscribe_token(email, language)
        return f"{settings.api_url.rstrip('/')}/api/{settings.api_version}/email/unsubscribe?token={token}"

    def render_announcement(self, campaign: str, email: str, language: str = Language.TR.value) -> Tuple[str, str, str, str]:
        """Render an announcement for one recipient: (subject, html, plain text, unsubscribe link)."""
        language = Language.EN.value if (language or '').upper() == Language.EN.value else Language.TR.value
        config = self.ANNOUNCEMENT_CONFIG[campaign][language]
        site = settings.frontend_url.rstrip('/')
        link = self.unsubscribe_link(email, language)
        html = self.jinja_env.get_template(config['template']).render(
            lang=language.lower(),
            asset_base=site,
            app_store_url=settings.app_store_url,
            unsubscribe_link=link,
        )
        text = config['text'].format(site=site, app_store=settings.app_store_url, unsubscribe=link)
        return config['subject'], html, text, link

    def send_announcement_email(self, campaign: str, email: str, language: str = Language.TR.value) -> bool:
        """
        Send an announcement to one address.

        Sent as a raw message so it can carry List-Unsubscribe headers (one-click unsubscribe).
        """
        try:
            subject, html, text, link = self.render_announcement(campaign, email, language)

            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = self.from_email
            message['To'] = email
            message['List-Unsubscribe'] = f"<{link}>"
            message['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
            message.attach(MIMEText(text, 'plain', 'utf-8'))
            message.attach(MIMEText(html, 'html', 'utf-8'))

            response = self.ses_client.send_raw_email(
                Source=self.from_email,
                Destinations=[email],
                RawMessage={'Data': message.as_string()},
            )
            logger.info(f"Announcement '{campaign}' sent to {email}. MessageId: {response['MessageId']}")
            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"Failed to send announcement '{campaign}' to {email}: {error_code} - {error_message}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending announcement '{campaign}' to {email}: {e}", exc_info=True)
            return False

    # ── draw life-cycle e-mails (created / joined / reminder) ──

    @classmethod
    def format_draw_date(cls, draw_date: Optional[datetime], language: str) -> Optional[str]:
        """
        Human readable draw time. Dates are stored in UTC; Turkish e-mails show Türkiye time
        (UTC+3 all year), English ones say UTC because the reader's time zone is unknown.
        """
        if not draw_date:
            return None
        if draw_date.tzinfo is None:
            draw_date = draw_date.replace(tzinfo=timezone.utc)
        if (language or '').upper() == Language.EN.value:
            local = draw_date.astimezone(timezone.utc)
            return f"{local.day} {cls.MONTHS['EN'][local.month - 1]} {local.year}, {local:%H:%M} UTC"
        local = draw_date.astimezone(timezone(timedelta(hours=3)))
        return f"{local.day} {cls.MONTHS['TR'][local.month - 1]} {local.year}, {local:%H:%M}"

    def render_draw_email(self, kind: str, draw: Draw, **extra) -> Tuple[str, str]:
        """Render one of the DRAW_EMAIL_CONFIG e-mails for a draw: (subject, html)."""
        language = Language.EN.value if (draw.language or '').upper() == Language.EN.value else Language.TR.value
        config = self.DRAW_EMAIL_CONFIG[kind]
        site = settings.frontend_url.rstrip('/')
        name = draw_display_name(draw.invite_code) or f"#{draw.id}"
        context = {
            'lang': language.lower(),
            'asset_base': site,
            'draw_name': name,
            'invite_code': draw.invite_code,
            'draw_date_text': self.format_draw_date(draw.draw_date, language),
            'invite_link': f"{site}/draw/join/{draw.invite_code}",
            'manage_link': f"{site}/draws/{draw.invite_code}",
            **extra,
        }
        html = self.jinja_env.get_template(config['template']).render(**context)
        return config['subject'][language].format(name=name), html

    def _send_html(self, to: str, subject: str, html: str, what: str) -> bool:
        """Send a single HTML e-mail; never raises."""
        try:
            response = self.ses_client.send_email(
                Source=self.from_email,
                Destination={'ToAddresses': [to]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {'Html': {'Data': html, 'Charset': 'UTF-8'}}
                }
            )
            logger.info(f"{what} e-mail sent to {to}. MessageId: {response['MessageId']}")
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"Failed to send {what} e-mail to {to}: {error_code} - {error_message}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending {what} e-mail to {to}: {e}", exc_info=True)
            return False

    def send_join_confirmation_email(self, participant: Participant, draw: Draw) -> bool:
        """Tell a participant they are on the list and when the draw takes place."""
        subject, html = self.render_draw_email(
            'join_confirmation', draw,
            participant_name=participant.first_name,
            status_link=self.reveal_link(participant, draw),
        )
        return self._send_html(participant.email, subject, html, 'Join confirmation')

    def send_draw_created_email(self, draw: Draw, email: str, organizer_name: str) -> bool:
        """Send the organizer the invite link, code and schedule of the draw they just created."""
        subject, html = self.render_draw_email('draw_created', draw, organizer_name=organizer_name)
        return self._send_html(email, subject, html, 'Draw created')

    def send_draw_reminder_email(self, draw: Draw, email: str, organizer_name: str, participant_count: int) -> bool:
        """Remind the organizer the day before the draw, with the number of participants so far."""
        subject, html = self.render_draw_email(
            'draw_reminder', draw, organizer_name=organizer_name, participant_count=participant_count
        )
        return self._send_html(email, subject, html, 'Draw reminder')

    def send_draw_not_run_email(self, draw: Draw, email: str, organizer_name: str, participant_count: int) -> bool:
        """Tell the organizer a scheduled draw could not run because fewer than 3 people joined."""
        subject, html = self.render_draw_email(
            'draw_not_run', draw, organizer_name=organizer_name, participant_count=participant_count
        )
        return self._send_html(email, subject, html, 'Draw not run')
