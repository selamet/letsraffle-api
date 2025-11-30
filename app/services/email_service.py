"""
Email Service Module

Email service using Amazon SES.
Creates HTML emails using Jinja2 template engine.
"""

import logging
from pathlib import Path
from typing import List, Dict, Tuple
import boto3
from botocore.exceptions import ClientError
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.config import settings
from app.models.draw import Draw, DrawResult, Participant, Language

logger = logging.getLogger(__name__)


class EmailService:
    """Email service using Amazon SES"""
    
    # Template configuration
    TEMPLATE_CONFIG = {
        Language.EN.value: {
            'template': 'email-template-en.html',
            'subject': '🎄 Secret Santa Draw Result',
            'not_provided': 'Not provided'
        },
        Language.TR.value: {
            'template': 'email-template-tr.html',
            'subject': '🎄 Yılbaşı Çekiliş Sonucu',
            'not_provided': 'Belirtilmemiş'
        }
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
    
    def _build_template_context(
        self,
        giver: Participant,
        receiver: Participant,
        language: str
    ) -> Dict[str, str]:
        """Build template context for email rendering"""
        config = self._get_template_config(language)
        not_provided = config['not_provided']
        
        return {
            'participant_name': f"{giver.first_name} {giver.last_name}",
            'target_name': f"{receiver.first_name} {receiver.last_name}",
            'target_email': receiver.email,
            'target_phone': receiver.phone or not_provided,
            'target_address': receiver.address or not_provided
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
            context = self._build_template_context(giver, receiver, draw.language)
            body_html = template.render(**context)
            
            response = self.ses_client.send_email(
                Source=self.from_email,
                Destination={'ToAddresses': [giver.email]},
                Message={
                    'Subject': {'Data': config['subject'], 'Charset': 'UTF-8'},
                    'Body': {'Html': {'Data': body_html, 'Charset': 'UTF-8'}}
                }
            )
            print(response)
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

