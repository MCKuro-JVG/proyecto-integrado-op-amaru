from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from .models import AgendaBlock, AppointmentReservation, Inquiry, SiteConfiguration


class AgendaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.day = timezone.localdate() + timedelta(days=1)
        self.worker = User.objects.create_user("agenda_worker")
        permissions = ["view_agendablock", "add_agendablock", "change_agendablock", "change_inquiry"]
        self.worker.user_permissions.add(*Permission.objects.filter(codename__in=permissions))

    def book(self, reason="Solicitud ficticia de agenda"):
        return self.client.post("/api/inquiries/", {
            "kind": "agenda", "day": self.day.isoformat(), "slot": "10:00",
            "name": "Persona ficticia", "phone": "+56900000000", "service": "Orientación",
            "reason": reason, "contact_authorized": True, "idempotency_key": str(uuid4()),
        }, content_type="application/json")

    def block(self, slot=None, active=True):
        data = {"day": self.day.isoformat(), "active": active}
        if slot:
            data["slot"] = slot
        return self.client.post("/api/agenda/blocks/", data, content_type="application/json")

    def slots(self):
        response = self.client.get("/api/agenda/")
        self.assertEqual(response.status_code, 200)
        return next((row["slots"] for row in response.json()["days"] if row["day"] == self.day.isoformat()), [])

    def test_block_authorization_and_release(self):
        self.assertEqual(self.block("10:00").status_code, 403)
        self.client.force_login(self.worker)
        self.assertEqual(self.block("10:00").status_code, 200)
        self.assertNotIn("10:00", self.slots())
        self.assertEqual(self.book().status_code, 409)
        self.assertFalse(Inquiry.objects.exists())
        self.assertEqual(self.block("10:00", False).status_code, 200)
        self.assertIn("10:00", self.slots())
        self.assertFalse(AgendaBlock.objects.get().active)

    def test_day_closure_and_weekly_hours(self):
        SiteConfiguration.objects.update_or_create(pk=1, defaults={"agenda_hours": {str(self.day.weekday()): ["10:00"]}})
        self.assertEqual(self.slots(), ["10:00"])
        self.client.force_login(self.worker)
        self.assertEqual(self.block().status_code, 200)
        self.assertEqual(self.slots(), [])
        self.assertEqual(self.book().status_code, 409)

    def test_public_calendar_includes_occupied_and_blocked_hours_without_reservation_details(self):
        SiteConfiguration.objects.update_or_create(
            pk=1, defaults={"agenda_hours": {str(self.day.weekday()): ["10:00", "11:00", "12:00"]}}
        )
        self.assertEqual(self.book().status_code, 201)
        self.client.force_login(self.worker)
        self.assertEqual(self.block("11:00").status_code, 200)
        self.client.logout()

        response = self.client.get("/api/agenda/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["calendar"]), 30)
        date = self.day.isoformat()
        self.assertEqual(next(row for row in data["calendar"] if row["day"] == date), {
            "day": date,
            "slots": [
                {"time": "10:00", "status": "occupied"},
                {"time": "11:00", "status": "blocked"},
                {"time": "12:00", "status": "available"},
            ],
        })
        self.assertEqual(next(row["slots"] for row in data["days"] if row["day"] == date), ["12:00"])
        self.assertNotContains(response, "Persona ficticia")

    def test_cancel_preserves_history_and_releases_slot(self):
        self.assertEqual(self.book().status_code, 201)
        self.assertNotIn("10:00", self.slots())
        self.client.force_login(self.worker)
        self.assertEqual(self.block().status_code, 409)
        inquiry = Inquiry.objects.get()
        response = self.client.patch(f"/api/inquiries/{inquiry.pk}/", {"status": "Cancelada"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentReservation.objects.exists())
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.status, "Cancelada")
        self.assertIn("10:00", self.slots())
        self.assertEqual(self.block().status_code, 200)
        response = self.client.patch(f"/api/inquiries/{inquiry.pk}/", {"status": "Nueva"}, content_type="application/json")
        self.assertEqual(response.status_code, 409)


class AgendaConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_booking_and_block_cannot_both_win(self):
        cache.clear()
        SiteConfiguration.objects.get_or_create(pk=1)
        worker = User.objects.create_user("agenda_race_worker")
        worker.user_permissions.add(*Permission.objects.filter(codename__in=["add_agendablock", "change_agendablock"]))
        day = (timezone.localdate() + timedelta(days=1)).isoformat()
        barrier = Barrier(2, timeout=10)

        def submit(block):
            try:
                client = Client()
                if block:
                    client.force_login(worker)
                barrier.wait()
                if block:
                    return client.post("/api/agenda/blocks/", {"day": day, "slot": "10:00"}, content_type="application/json").status_code
                data = {"kind": "agenda", "day": day, "slot": "10:00", "name": "Carrera ficticia",
                        "phone": "+56900000000", "service": "Orientación", "reason": "Prueba concurrente",
                        "contact_authorized": True, "idempotency_key": str(uuid4())}
                return client.post("/api/inquiries/", data, content_type="application/json").status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            statuses = set(workers.map(submit, [True, False]))
        self.assertIn(statuses, [{200, 409}, {201, 409}])
        self.assertEqual(AgendaBlock.objects.filter(active=True).count() + AppointmentReservation.objects.count(), 1)
