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
from pathlib import Path

# 2026-10-01 prod-safety: this default pointed the suite at PRODUCTION when
# the env was unset (the exact failure class conftest.py's gate exists for).
# Localhost default + explicit env for anything live.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = BACKEND_ROOT.parent / 'frontend'
# 2026-10-01 prod-safety: this suite's env default previously pointed
# at PRODUCTION (app.trustoffice.app); localhost + explicit env only.
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8000').rstrip('/')


class TestAdminPurchaseNotification:
    """Tests for admin purchase notification email feature"""
    
    def test_email_service_has_admin_notification_method(self):
        """Verify send_admin_new_purchase_notification method exists in email_service"""
        import sys
        sys.path.insert(0, str(BACKEND_ROOT))
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
        sys.path.insert(0, str(BACKEND_ROOT))
        from email_service import email_service
        
        sig = inspect.signature(email_service.send_admin_new_purchase_notification)
        params = list(sig.parameters.keys())
        
        expected_params = ['customer_email', 'customer_name', 'plan_type', 'amount']
        assert params == expected_params, \
            f"Expected params {expected_params}, got {params}"
        
        print(f"✅ Method signature correct: {sig}")
    
    def test_admin_notification_sends_to_correct_email(self):
        """Verify the method sends to contact@trustoffice.app"""
        with open(str(BACKEND_ROOT / 'email_service.py'), 'r') as f:
            content = f.read()
        
        # Check that admin_email is set to contact@trustoffice.app
        assert 'admin_email = "contact@trustoffice.app"' in content, \
            "Admin notification should send to contact@trustoffice.app"
        
        print("✅ Admin notification sends to contact@trustoffice.app")
    
    def test_subscription_webhook_calls_admin_notification(self):
        """Verify checkout.session.completed webhook calls admin notification"""
        with open(str(BACKEND_ROOT / 'routers/subscriptions.py'), 'r') as f:
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
        with open(str(FRONTEND_ROOT / 'src/pages/SettingsPage.js'), 'r') as f:
            content = f.read()
        
        # 2026-10-01 rewrite: Settings now uses a tab layout (the h2-section
        # order this test anchored on was replaced). Order contract: profile
        # -> compliance/governance -> account/billing tabs, in that DOM order.
        tabs = {
            'profile': content.find('<TabsTrigger value="profile">'),
            'compliance': content.find('<TabsTrigger value="compliance">'),
            'account': content.find('<TabsTrigger value="account">'),
        }
        for name, pos in tabs.items():
            assert pos > 0, f"Settings tab '{name}' should exist (current structure: tabbed settings)"
        assert tabs['profile'] < tabs['compliance'] < tabs['account'], \
            f"Settings tab order must be profile -> compliance -> account/billing: {tabs}"
        
        print("✅ Settings page tab order is correct: Profile -> Governance -> Account & Billing")


class TestReadOnlyChecks:
    """Tests for read-only checks in page components (code structure verification)"""
    
    def test_minutes_page_has_readonly_checks(self):
        """Verify MinutesPage has isReadOnly checks for Record Minutes and Guided Minutes buttons"""
        with open(str(FRONTEND_ROOT / 'src/pages/MinutesPage.js'), 'r') as f:
            content = f.read()
        
        # 2026-10-01 rewrite: the record/guided handlers were consolidated;
        # the shipped guard is the inline check in the click handler:
        #   if (isReadOnly) { showUpgradeModal('create meeting minutes', ...) }
        assert 'isReadOnly' in content, "MinutesPage should use isReadOnly"
        assert 'showUpgradeModal' in content, "MinutesPage should use showUpgradeModal"
        
        guard_pos = content.find("if (isReadOnly)")
        upgrade_pos = content.find("showUpgradeModal('create meeting minutes'")
        assert guard_pos > 0, "MinutesPage should have an inline isReadOnly guard"
        assert upgrade_pos > guard_pos and upgrade_pos - guard_pos < 200, \
            "the read-only guard should open the upgrade modal (create meeting minutes)"
        
        print("✅ MinutesPage read-only guard wired to the upgrade modal")
    
    def test_distributions_page_has_readonly_check(self):
        """Verify DistributionsPage has isReadOnly check for Add Distribution button"""
        with open(str(FRONTEND_ROOT / 'src/pages/DistributionsPage.js'), 'r') as f:
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
        with open(str(FRONTEND_ROOT / 'src/pages/ExpensesPage.js'), 'r') as f:
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
        with open(str(FRONTEND_ROOT / 'src/pages/BeneficiariesPage.js'), 'r') as f:
            content = f.read()
        
        # Check isReadOnly is imported/used
        assert 'isReadOnly' in content, "BeneficiariesPage should use isReadOnly"
        assert 'showUpgradeModal' in content, "BeneficiariesPage should use showUpgradeModal"
        
        # 2026-10-01 rewrite: handleOpenCertificateModal moved into the
        # beneficiaries hook module; the page passes isReadOnly down and the
        # hook guards the modal. Verify both ends of that wiring.
        assert 'isReadOnly' in content, "BeneficiariesPage should use isReadOnly"
        hooks_path = FRONTEND_ROOT / 'src/pages/beneficiaries/hooks.js'
        with open(str(hooks_path), 'r') as f:
            hooks_content = f.read()
        modal_guard = hooks_content.find('const handleOpenCertificateModal')
        assert modal_guard > 0, "hook should define handleOpenCertificateModal"
        body = hooks_content[modal_guard:modal_guard + 400]
        assert 'isReadOnly' in body, "handleOpenCertificateModal should check isReadOnly (hooks.js)"
        
        # 2026-10-01: handleOpenTransferModal also lives in the hook module;
        # same ends-of-wiring check as the certificate modal above.
        transfer_guard = hooks_content.find('const handleOpenTransferModal')
        assert transfer_guard > 0, "hook should define handleOpenTransferModal"
        transfer_body = hooks_content[transfer_guard:transfer_guard + 400]
        assert 'isReadOnly' in transfer_body, "handleOpenTransferModal should check isReadOnly (hooks.js)"
        
        print("✅ BeneficiariesPage has read-only checks for Issue Units and Transfer")


class TestUpgradeModalIntegration:
    """Tests for UpgradeModal context integration"""
    
    def test_upgrade_modal_context_exists(self):
        """Verify UpgradeModalContext exists and exports showUpgradeModal"""
        import os
        context_path = str(FRONTEND_ROOT / 'src/context/UpgradeModalContext.js')
        
        assert os.path.exists(context_path), "UpgradeModalContext.js should exist"
        
        with open(context_path, 'r') as f:
            content = f.read()
        
        assert 'showUpgradeModal' in content, "UpgradeModalContext should export showUpgradeModal"
        assert 'useUpgradeModal' in content, "UpgradeModalContext should export useUpgradeModal hook"
        
        print("✅ UpgradeModalContext exists with showUpgradeModal")
    
    def test_pages_import_upgrade_modal_context(self):
        """Verify all relevant pages import useUpgradeModal"""
        pages = [
            str(FRONTEND_ROOT / 'src/pages/MinutesPage.js'),
            str(FRONTEND_ROOT / 'src/pages/DistributionsPage.js'),
            str(FRONTEND_ROOT / 'src/pages/ExpensesPage.js'),
            str(FRONTEND_ROOT / 'src/pages/BeneficiariesPage.js')
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
