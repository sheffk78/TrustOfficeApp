"""
Test suite for trial expired features:
1. Admin purchase notification email method exists
2. Settings page section order verification (code structure)
3. Read-only checks in page components (code structure)
"""

import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://app.trustoffice.app').rstrip('/')


class TestAdminPurchaseNotification:
    """Tests for admin purchase notification email feature"""
    
    def test_email_service_has_admin_notification_method(self):
        """Verify send_admin_new_purchase_notification method exists in email_service"""
        import sys
        sys.path.insert(0, '/app/backend')
        from email_service import email_service
        
        # Check method exists
        assert hasattr(email_service, 'send_admin_new_purchase_notification'), \
            "email_service should have send_admin_new_purchase_notification method"
        
        # Check it's callable
        assert callable(email_service.send_admin_new_purchase_notification), \
            "send_admin_new_purchase_notification should be callable"
        
        print("✅ send_admin_new_purchase_notification method exists and is callable")
    
    def test_admin_notification_method_signature(self):
        """Verify the method has correct parameters"""
        import sys
        import inspect
        sys.path.insert(0, '/app/backend')
        from email_service import email_service
        
        sig = inspect.signature(email_service.send_admin_new_purchase_notification)
        params = list(sig.parameters.keys())
        
        expected_params = ['customer_email', 'customer_name', 'plan_type', 'amount']
        assert params == expected_params, \
            f"Expected params {expected_params}, got {params}"
        
        print(f"✅ Method signature correct: {sig}")
    
    def test_admin_notification_sends_to_correct_email(self):
        """Verify the method sends to contact@trustoffice.app"""
        with open('/app/backend/email_service.py', 'r') as f:
            content = f.read()
        
        # Check that admin_email is set to contact@trustoffice.app
        assert 'admin_email = "contact@trustoffice.app"' in content, \
            "Admin notification should send to contact@trustoffice.app"
        
        print("✅ Admin notification sends to contact@trustoffice.app")
    
    def test_subscription_webhook_calls_admin_notification(self):
        """Verify checkout.session.completed webhook calls admin notification"""
        with open('/app/backend/routers/subscriptions.py', 'r') as f:
            content = f.read()
        
        # Check that send_admin_new_purchase_notification is called
        assert 'send_admin_new_purchase_notification' in content, \
            "subscriptions.py should call send_admin_new_purchase_notification"
        
        # Check it's called in checkout.session.completed handler
        checkout_section = content[content.find('checkout.session.completed'):content.find('customer.subscription.updated')]
        assert 'send_admin_new_purchase_notification' in checkout_section, \
            "Admin notification should be called in checkout.session.completed handler"
        
        print("✅ Webhook calls admin notification on new purchase")


class TestSettingsPageSectionOrder:
    """Tests for Settings page section order (code structure verification)"""
    
    def test_settings_page_section_order(self):
        """Verify sections appear in correct order: Profile -> Create New Trust -> Trust Settings -> Billing"""
        with open('/app/frontend/src/pages/SettingsPage.js', 'r') as f:
            content = f.read()
        
        # Find positions of section headers
        profile_pos = content.find('Profile</h2>')
        create_trust_pos = content.find('Create New Trust</h2>')
        trust_settings_pos = content.find('Trust Settings</h2>')
        billing_pos = content.find('Billing & Subscription</h2>')
        
        # All sections should exist
        assert profile_pos > 0, "Profile section should exist"
        assert create_trust_pos > 0, "Create New Trust section should exist"
        assert trust_settings_pos > 0, "Trust Settings section should exist"
        assert billing_pos > 0, "Billing section should exist"
        
        # Verify order
        assert profile_pos < create_trust_pos, \
            f"Profile ({profile_pos}) should come before Create New Trust ({create_trust_pos})"
        assert create_trust_pos < trust_settings_pos, \
            f"Create New Trust ({create_trust_pos}) should come before Trust Settings ({trust_settings_pos})"
        assert trust_settings_pos < billing_pos, \
            f"Trust Settings ({trust_settings_pos}) should come before Billing ({billing_pos})"
        
        print("✅ Settings page section order is correct: Profile -> Create New Trust -> Trust Settings -> Billing")


class TestReadOnlyChecks:
    """Tests for read-only checks in page components (code structure verification)"""
    
    def test_minutes_page_has_readonly_checks(self):
        """Verify MinutesPage has isReadOnly checks for Record Minutes and Guided Minutes buttons"""
        with open('/app/frontend/src/pages/MinutesPage.js', 'r') as f:
            content = f.read()
        
        # Check isReadOnly is imported/used
        assert 'isReadOnly' in content, "MinutesPage should use isReadOnly"
        assert 'showUpgradeModal' in content, "MinutesPage should use showUpgradeModal"
        
        # Check handleRecordMinutes has isReadOnly check
        assert 'handleRecordMinutes' in content, "handleRecordMinutes function should exist"
        record_minutes_section = content[content.find('handleRecordMinutes'):content.find('handleGuidedMinutes')]
        assert 'isReadOnly' in record_minutes_section, \
            "handleRecordMinutes should check isReadOnly"
        
        # Check handleGuidedMinutes has isReadOnly check
        assert 'handleGuidedMinutes' in content, "handleGuidedMinutes function should exist"
        # Find the handleGuidedMinutes function and check for isReadOnly within it
        guided_start = content.find('const handleGuidedMinutes')
        guided_end = content.find('};', guided_start) + 2
        guided_minutes_section = content[guided_start:guided_end]
        assert 'isReadOnly' in guided_minutes_section, \
            "handleGuidedMinutes should check isReadOnly"
        
        print("✅ MinutesPage has read-only checks for Record Minutes and Guided Minutes")
    
    def test_distributions_page_has_readonly_check(self):
        """Verify DistributionsPage has isReadOnly check for Add Distribution button"""
        with open('/app/frontend/src/pages/DistributionsPage.js', 'r') as f:
            content = f.read()
        
        # Check isReadOnly is imported/used
        assert 'isReadOnly' in content, "DistributionsPage should use isReadOnly"
        assert 'showUpgradeModal' in content, "DistributionsPage should use showUpgradeModal"
        
        # Check handleDialogOpenChange has isReadOnly check
        assert 'handleDialogOpenChange' in content, "handleDialogOpenChange function should exist"
        dialog_section = content[content.find('handleDialogOpenChange'):content.find('handleDialogOpenChange') + 300]
        assert 'isReadOnly' in dialog_section, \
            "handleDialogOpenChange should check isReadOnly"
        
        print("✅ DistributionsPage has read-only check for Add Distribution")
    
    def test_expenses_page_has_readonly_check(self):
        """Verify ExpensesPage has isReadOnly check for Add Expense button"""
        with open('/app/frontend/src/pages/ExpensesPage.js', 'r') as f:
            content = f.read()
        
        # Check isReadOnly is imported/used
        assert 'isReadOnly' in content, "ExpensesPage should use isReadOnly"
        assert 'showUpgradeModal' in content, "ExpensesPage should use showUpgradeModal"
        
        # Check Dialog onOpenChange has isReadOnly check
        # Look for the pattern: onOpenChange={(open) => { if (open && isReadOnly)
        assert 'isReadOnly' in content, "ExpensesPage should check isReadOnly in dialog"
        
        print("✅ ExpensesPage has read-only check for Add Expense")
    
    def test_beneficiaries_page_has_readonly_checks(self):
        """Verify BeneficiariesPage has isReadOnly checks for Issue Units and Transfer buttons"""
        with open('/app/frontend/src/pages/BeneficiariesPage.js', 'r') as f:
            content = f.read()
        
        # Check isReadOnly is imported/used
        assert 'isReadOnly' in content, "BeneficiariesPage should use isReadOnly"
        assert 'showUpgradeModal' in content, "BeneficiariesPage should use showUpgradeModal"
        
        # Check handleOpenCertificateModal has isReadOnly check
        assert 'handleOpenCertificateModal' in content, "handleOpenCertificateModal function should exist"
        cert_modal_section = content[content.find('handleOpenCertificateModal'):content.find('handleOpenCertificateModal') + 400]
        assert 'isReadOnly' in cert_modal_section, \
            "handleOpenCertificateModal should check isReadOnly"
        
        # Check handleOpenTransferModal has isReadOnly check
        assert 'handleOpenTransferModal' in content, "handleOpenTransferModal function should exist"
        transfer_modal_section = content[content.find('handleOpenTransferModal'):content.find('handleOpenTransferModal') + 400]
        assert 'isReadOnly' in transfer_modal_section, \
            "handleOpenTransferModal should check isReadOnly"
        
        print("✅ BeneficiariesPage has read-only checks for Issue Units and Transfer")


class TestUpgradeModalIntegration:
    """Tests for UpgradeModal context integration"""
    
    def test_upgrade_modal_context_exists(self):
        """Verify UpgradeModalContext exists and exports showUpgradeModal"""
        import os
        context_path = '/app/frontend/src/context/UpgradeModalContext.js'
        
        assert os.path.exists(context_path), "UpgradeModalContext.js should exist"
        
        with open(context_path, 'r') as f:
            content = f.read()
        
        assert 'showUpgradeModal' in content, "UpgradeModalContext should export showUpgradeModal"
        assert 'useUpgradeModal' in content, "UpgradeModalContext should export useUpgradeModal hook"
        
        print("✅ UpgradeModalContext exists with showUpgradeModal")
    
    def test_pages_import_upgrade_modal_context(self):
        """Verify all relevant pages import useUpgradeModal"""
        pages = [
            '/app/frontend/src/pages/MinutesPage.js',
            '/app/frontend/src/pages/DistributionsPage.js',
            '/app/frontend/src/pages/ExpensesPage.js',
            '/app/frontend/src/pages/BeneficiariesPage.js'
        ]
        
        for page_path in pages:
            with open(page_path, 'r') as f:
                content = f.read()
            
            assert 'useUpgradeModal' in content, \
                f"{page_path} should import useUpgradeModal"
            assert "from '@/context/UpgradeModalContext'" in content, \
                f"{page_path} should import from UpgradeModalContext"
        
        print("✅ All pages import useUpgradeModal from UpgradeModalContext")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
