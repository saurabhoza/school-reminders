"""Opt-in Groq smoke test using a synthetic email and the local API key."""

import unittest

from school_reminders.domain.email_message import EmailMessage
from school_reminders.extraction import extract_notices
from school_reminders.groq_model import GroqNoticeModel, groq_api_key


@unittest.skipUnless(groq_api_key(), "GROQ_API_KEY is required")
class LiveGroqTests(unittest.TestCase):
    def test_class_trip_and_school_closure(self):
        email = EmailMessage(message_id="synthetic", thread_id="", internal_date_ms="",
                             rfc_message_id="", sender="", subject="School notices", date="",
                             text=("Newsletter issued 8 May.\nMaple class will visit the museum on 12 May.\n"
                                   "All classes finish early on 13 May.\nPlease check at home and return "
                                   "missing books as soon as possible. Donations are also welcome."),
                             html="", raw_base64url="")
        with GroqNoticeModel.open() as model:
            notices = extract_notices(model, email)
        self.assertEqual(len(notices), 2)
        self.assertEqual({n["event_date"] for n in notices}, {"12 May", "13 May"})
        self.assertTrue(any(n["audience"]["classes"] == ["Maple"] and not n["audience"]["years"]
                            for n in notices))
        self.assertTrue(any(n["audience"]["whole_school"] for n in notices))
