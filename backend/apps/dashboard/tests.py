from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class DashboardTests(TestCase):
    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_dashboard_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(
            username="dashboard-user", password="clave-de-prueba-segura"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ARNOLD")
        self.assertContains(response, 'id="sidebarToggle"')
        self.assertContains(response, 'aria-controls="sheetSidebar"')
        self.assertContains(response, 'id="focusToggle"')
        self.assertContains(response, 'id="gridWrap"')
        self.assertContains(response, 'id="saveButton"')
        self.assertContains(response, 'id="downloadClean"')
        self.assertContains(response, 'id="downloadProblems"')
        self.assertContains(response, 'id="formatToolbar"')
        self.assertContains(response, 'id="gridContextMenu"')
        self.assertContains(response, 'id="rangeAddress"')
        html = response.content.decode()
        self.assertLess(html.index("js/worksheet-grid-model.js"), html.index("js/worksheet-grid.js"))
        self.assertLess(html.index("js/worksheet-grid.js"), html.index("js/worksheet-app.js"))

    def test_health_endpoint(self):
        response = self.client.get(reverse("dashboard:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_clean_layout_asks_reason_only_in_confirmation_dialog(self):
        self.client.force_login(get_user_model().objects.create_user(username="confirmation-reviewer"))
        response = self.client.get(reverse("dashboard:index"))
        html = response.content.decode()
        self.assertNotContains(response, 'id="sheetHint"')
        self.assertNotContains(response, 'class="edit-bar"')
        self.assertNotContains(response, 'id="sidebarToggleText"')
        self.assertNotContains(response, 'Clic: seleccionar')
        self.assertContains(response, 'aria-label="Ocultar menú"')
        self.assertEqual(html.count('id="changeReason"'), 1)
        self.assertLess(html.index('id="confirmChangesDialog"'), html.index('id="changeReason"'))
        self.assertLess(html.index('id="changeReason"'), html.index('id="uploadDialog"'))
        for control in ("confirmChangesForm", "cancelChanges", "confirmSave", "confirmSaveDownload"):
            self.assertContains(response, f'id="{control}"')

    def test_format_tools_are_floating_hidden_and_all_features_remain(self):
        self.client.force_login(get_user_model().objects.create_user(username="floating-reviewer"))
        response = self.client.get(reverse("dashboard:index"))
        html = response.content.decode()
        self.assertContains(response, 'aria-label="Formato de la selección" hidden')
        self.assertGreater(html.index('id="formatToolbar"'), html.index('id="sheetSecondary"'))
        for control in ["rangeAddress", "selectRange", "fontSize", "textColor", "fillColor",
                        "cellAlignment", "clearFormat", "selectRow", "selectColumn", "clearSelection",
                        "autoWidth", "autoHeight", "showFullText", "resetSizes", "sheetZoom",
                        "formatStatus", "formatSave", "formatRefresh", "copySelection", "undoDraft"]:
            self.assertEqual(html.count(f'id="{control}"'), 1)
        for panel in ["fillPalette", "textPalette", "alignmentPanel", "sizePanel", "morePanel"]:
            self.assertContains(response, f'aria-controls="{panel}"')
        for style in ["bold", "italic", "underline", "wrap"]:
            self.assertContains(response, f'data-format="{style}"')

    def test_preliminary_grid_precedes_secondary_summary(self):
        user = get_user_model().objects.create_user(username="layout-reviewer")
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))
        html = response.content.decode()
        self.assertLess(html.index('id="gridView"'), html.index('id="sheetSecondary"'))
        self.assertLess(html.index('id="historyView"'), html.index('id="sheetSecondary"'))
        self.assertLess(html.index('id="sheetSecondary"'), html.index('id="sheetStats"'))
        self.assertLess(html.index('id="sheetStats"'), html.index('id="skippedRules"'))
        self.assertEqual(html.count('id="sheetStats"'), 1)
        self.assertEqual(html.count('id="saveBadge"'), 1)
        self.assertContains(response, 'id="toolbarSaveStatus"')
        self.assertContains(response, 'href="#sheetSecondary"')

