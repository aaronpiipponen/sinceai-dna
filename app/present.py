# -*- coding: utf-8 -*-
"""Presentation layer for the demo and lab.

One job: turn a validated protocol reply plus the conversation state into the
`display` block of `docs/UI_SPEC.md` section 5. Everything the end user reads
comes from here, already localised to fi / en / sv, so the frontend only
renders and never invents a content label.

    from present import display
    block = display(visible_case, state, reply, "fi")

Pure functions, no model calls, standard library only.

Rules that shape this module:

* No ids leave here. Action ids, topic ids, signal paths, guidance ids, risk
  enums, case ids and confidence never appear in a display value. Consent
  fields are addressed by an opaque token (`s1`, `s2`, ...) that
  `resolve_fields()` maps back to a signal path on the server.
* `signals.artifact` is written by whoever sent the message, often a scammer.
  It is shown as plain text and never interpreted; links stay text.
* An attachment and the visibility card are shown for every reply type; the
  other blocks are null unless the reply type uses them.
"""

import datetime
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
GUIDANCE_PATH = os.path.join(PROJECT, "DNA_Digital_Security_Assistant_SimSet_v2.0.1",
                             "data", "reference", "guidance_corpus.jsonl")

LANGUAGES = ("fi", "en", "sv")
RISK_LEVELS = ("none", "low", "medium", "high", "critical")
URGENCIES = ("none", "routine", "today", "immediate")


def L(fi, en, sv):
    """One localised string. sv is real Swedish, never a copy of en."""
    return {"fi": fi, "en": en, "sv": sv}


def _pick(table, lang):
    return table.get(lang) or table["en"]


def _s(value):
    return value.strip() if isinstance(value, str) else ""


def _clip(text, limit=200):
    """Collapse whitespace and cut on a word boundary with an ellipsis."""
    text = " ".join(_s(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:.-") + "…"


# --- tables -----------------------------------------------------------------

# Short imperative headlines, not the vocabulary's long sentences. "What do I
# do now?", in the user's words.
ACTIONS = {
    "no_action_needed": L("Näyttää aidolta – sinun ei tarvitse tehdä mitään",
                          "This looks genuine – there's nothing you need to do",
                          "Det här verkar äkta – du behöver inte göra något"),
    "do_not_interact_and_delete": L("Älä reagoi viestiin – poista se",
                                    "Don't respond – just delete it",
                                    "Reagera inte – radera meddelandet"),
    "verify_via_official_channel": L("Tarkista asia suoraan oikealta palvelulta",
                                     "Check it directly with the real company",
                                     "Kolla saken direkt med det riktiga företaget"),
    "contact_operator_support": L("Ota yhteyttä asiakaspalveluumme",
                                  "Contact our customer service",
                                  "Kontakta vår kundtjänst"),
    "change_password_and_enable_mfa": L("Vaihda salasana ja ota käyttöön kaksivaiheinen tunnistautuminen",
                                        "Change your password and turn on two-step verification",
                                        "Byt lösenord och slå på tvåstegsverifiering"),
    "isolate_device_and_scan": L("Irrota laite verkosta ja tarkistuta se",
                                 "Take the device offline and get it checked",
                                 "Koppla bort enheten från nätet och låt någon kolla den"),
    "contact_bank_and_block_cards": L("Ota heti yhteyttä pankkiisi",
                                      "Contact your bank now",
                                      "Kontakta din bank nu"),
    "report_to_authority": L("Ilmoita asiasta viranomaisille",
                             "Report it to the authorities",
                             "Anmäl det till myndigheterna"),
    "escalate_to_human": L("Asiantuntija auttaa sinua tästä eteenpäin",
                           "A specialist will help you from here",
                           "En specialist hjälper dig vidare"),
    "decline_out_of_scope": L("Tässä en voi auttaa – mutta näin pääset eteenpäin",
                              "I can't help with that – but here's what you can do",
                              "Det kan jag inte hjälpa till med – men så här kan du göra"),
}

URGENCY_LABELS = {
    "immediate": L("Toimi heti", "Act now", "Agera nu"),
    "today": L("Toimi tänään", "Act today", "Agera i dag"),
    "routine": L("Toimi kun ehdit", "When you can", "När du hinner"),
    "none": L("Ei vaadi toimia", "Nothing to do", "Inget att göra"),
}

ATTACHMENT_KINDS = {
    "sms": L("Tekstiviesti", "Text message", "Sms"),
    "email": L("Sähköposti", "Email", "E-post"),
    "call": L("Puhelu", "Call", "Samtal"),
    "letter": L("Kirje", "Letter", "Brev"),
    "notification": L("Ilmoitus", "Notification", "Avisering"),
}

# The case schema's artifact types, mapped onto the five kinds the UI draws.
_ARTIFACT_KIND = {
    "sms": "sms", "email": "email", "call": "call", "letter": "letter",
    "push_notification": "notification", "notification": "notification",
    "chat": "sms", "user_report": "notification", "screen_note": "notification",
    "social_ad": "notification",
}

# Plain labels for every signal path the answer may honestly claim to have used.
SIGNALS = {
    "artifact": L("Lähettämäsi viesti", "The message you sent", "Meddelandet du skickade"),
    "link_check": L("Linkkitarkistus", "Link check", "Länkkontroll"),
    "call_warning": L("Puheluvaroitus", "Call warning", "Samtalsvarning"),
    "user_call_notes": L("Muistiinpanosi puhelusta", "Your notes about the call",
                         "Dina anteckningar om samtalet"),
    "subscription.products": L("Liittymäsi tuotteet", "Your subscriptions", "Dina abonnemang"),
    "subscription.recent_events": L("Liittymän viimeisimmät muutokset",
                                    "Recent changes to your subscription",
                                    "Senaste ändringar i abonnemanget"),
    "subscription.network_status": L("Liittymäsi verkkoyhteys", "Your line's network connection",
                                     "Abonnemangets nätanslutning"),
    "device.summary": L("Laitteesi perustiedot", "Your device details", "Uppgifter om din enhet"),
    "device.recent_app_installs": L("Viimeksi asennetut sovellukset",
                                    "Recently installed apps", "Nyligen installerade appar"),
    "device.security_findings": L("Tietoturvasovelluksen havainnot",
                                  "What the security app found", "Vad säkerhetsappen hittat"),
    "operator_account.recent_logins": L("Viimeaikaiset kirjautumiset",
                                        "Recent sign-ins", "Senaste inloggningar"),
    "credential_exposure": L("Sähköpostin vuototarkistus", "Email breach check",
                             "Kontroll av e-postläckor"),
    "business.profile": L("Yrityksesi perustiedot", "Your business details",
                          "Uppgifter om ditt företag"),
    "business.staff_accounts": L("Yrityksen käyttäjätilit", "Your business user accounts",
                                 "Företagets användarkonton"),
}

# One line each: what, how far back, why. Keyed by every consent-gated path
# that occurs in dev, test or the the five sample journeys.
CONSENT = {
    "subscription.network_status": {
        "label": SIGNALS["subscription.network_status"],
        "question": L("Saanko katsoa, onko liittymässäsi verkkoyhteyttä?",
                      "May I check whether your line has a network connection?",
                      "Får jag kontrollera om ditt abonnemang har nätanslutning?"),
        "purpose": L("Katson, onko liittymässäsi juuri nyt verkkoyhteyttä, jotta tiedän, "
                     "onko kyse katkoksesta vai kaappauksesta.",
                     "I'll check whether your line has network service right now, so I can "
                     "tell an outage from a takeover.",
                     "Jag kontrollerar om ditt abonnemang har nättäckning just nu, så att jag "
                     "kan skilja ett avbrott från en kapning."),
    },
    "subscription.recent_events": {
        "label": SIGNALS["subscription.recent_events"],
        "question": L("Saanko katsoa liittymäsi viimeisimmät muutokset?",
                      "May I check the recent changes to your subscription?",
                      "Får jag kontrollera de senaste ändringarna i ditt abonnemang?"),
        "purpose": L("Katson liittymäsi SIM-, eSIM- ja tilausmuutokset viimeisen 14 päivän "
                     "ajalta, jotta näen, onko joku tehnyt muutoksia sinun nimissäsi.",
                     "I'll look at SIM, eSIM and order changes on your subscription from the "
                     "last 14 days, to see whether someone changed something in your name.",
                     "Jag tittar på SIM-, eSIM- och beställningsändringar i ditt abonnemang de "
                     "senaste 14 dagarna, för att se om någon ändrat något i ditt namn."),
    },
    "device.recent_app_installs": {
        "label": SIGNALS["device.recent_app_installs"],
        "question": L("Saanko katsoa viimeksi asennetut sovelluksesi?",
                      "May I check your recently installed apps?",
                      "Får jag kontrollera dina nyligen installerade appar?"),
        "purpose": L("Katson viimeisen 14 päivän aikana asennetut sovellukset ja niiden "
                     "oikeudet, jotta näen, onko puhelimeesi tullut jotain, mitä et asentanut.",
                     "I'll look at apps installed in the last 14 days and their permissions, "
                     "to see whether something you didn't install is on your phone.",
                     "Jag tittar på appar som installerats de senaste 14 dagarna och deras "
                     "behörigheter, för att se om något du inte installerat finns på din telefon."),
    },
    "device.security_findings": {
        "label": SIGNALS["device.security_findings"],
        "question": L("Saanko katsoa, mitä tietoturvasovellus on löytänyt?",
                      "May I check what the security app has found?",
                      "Får jag kolla vad säkerhetsappen har hittat?"),
        "purpose": L("Katson, onko tietoturvasovellus löytänyt puhelimestasi esimerkiksi "
                     "etäkäyttöohjelmia, jotta näen, onko joku päässyt laitteeseesi.",
                     "I'll look at findings from the device's security app about remote-access "
                     "tools, to see whether someone got into your phone.",
                     "Jag tittar på om säkerhetsappen har hittat till exempel fjärrstyrningsprogram "
                     "på din telefon, för att se om någon kommit åt den."),
    },
    "operator_account.recent_logins": {
        "label": SIGNALS["operator_account.recent_logins"],
        "question": L("Saanko tarkistaa viimeaikaiset kirjautumisesi?",
                      "May I check your recent sign-ins?",
                      "Får jag kontrollera dina senaste inloggningar?"),
        "purpose": L("Katson tilillesi tehdyt kirjautumiset viimeisen 7 päivän ajalta, jotta "
                     "näen, onko joku muu kirjautunut sisään.",
                     "I'll look at sign-ins to your account from the last 7 days, to "
                     "see whether someone else got in.",
                     "Jag tittar på inloggningar till ditt konto de senaste 7 dagarna, "
                     "för att se om någon annan loggat in."),
    },
    "credential_exposure": {
        "label": SIGNALS["credential_exposure"],
        "question": L("Saanko tarkistaa, onko sähköpostisi vuotanut?",
                      "May I check whether your email has appeared in a breach?",
                      "Får jag kontrollera om din e-post har läckt?"),
        "purpose": L("Tarkistan, onko sähköpostiosoitteesi näkynyt tunnetuissa tietovuodoissa, "
                     "jotta tiedän, pitääkö salasana vaihtaa.",
                     "I'll check whether your email address appears in known data breaches, so "
                     "I know whether the password needs changing.",
                     "Jag kontrollerar om din e-postadress finns i kända dataläckor, så att jag "
                     "vet om lösenordet behöver bytas."),
    },
    "business.staff_accounts": {
        "label": SIGNALS["business.staff_accounts"],
        "question": L("Saanko katsoa yrityksesi käyttäjätilit?",
                      "May I check your business user accounts?",
                      "Får jag kontrollera företagets användarkonton?"),
        "purpose": L("Katson yrityksesi käyttäjätilit ja niiden viimeisimmän käytön, jotta "
                     "näen, onko käytössä tilejä, joita siellä ei pitäisi olla.",
                     "I'll look at your business user accounts and when they were last used, "
                     "to see whether any account shouldn't be there.",
                     "Jag tittar på företagets användarkonton och när de senast användes, för "
                     "att se om något konto inte borde finnas."),
    },
}

ESCALATION_TARGETS = {
    "operator_support_agent": L("Operaattorin asiakaspalvelu", "Operator customer service",
                                "Operatörens kundtjänst"),
    "security_specialist": L("Tietoturva-asiantuntija", "Security specialist",
                             "Säkerhetsspecialist"),
    "business_security_support": L("Yrityksen tietoturvatuki", "Business security support",
                                   "Företagets säkerhetsstöd"),
    "human_advisor": L("Koulutettu neuvonantaja", "Trained advisor", "Utbildad rådgivare"),
}

CONSENT_TITLE = L("Saanko katsoa näitä tietoja?", "May I look at these details?",
                  "Får jag titta på de här uppgifterna?")
CONSENT_FINE = L("Saat silti neuvon, vaikka kieltäytyisit.",
                 "You'll still get advice if you say no.",
                 "Du får råd även om du säger nej.")
CONSENT_ALLOW = L("Salli", "Allow", "Tillåt")
CONSENT_DENY = L("Älä salli", "Don't allow", "Tillåt inte")

QUICK_REPLIES = {
    "fi": ("Kyllä", "Ei", "En ole varma"),
    "en": ("Yes", "No", "Not sure"),
    "sv": ("Ja", "Nej", "Vet inte"),
}

# A closed yes/no question, judged from its opening only: Finnish verb with
# -ko/-kö, English auxiliary first, Swedish finite verb first. Topic chips
# answer a yes/no question about that topic; under an open question they would
# claim the user was asked something they were not, so open questions get one
# honest fallback chip instead.
_YES_NO = {
    "fi": re.compile(r"^\s*[A-Za-zÅÄÖåäö]+\s*(?:ko|kö)\b", re.I),
    "en": re.compile(r"^\s*(?:did|do|does|have|has|are|is|was|were|can|could|"
                     r"would|should|will|may)\b", re.I),
    "sv": re.compile(r"^\s*(?:har|är|gjorde|skrev|kan|var|står|hade)\b", re.I),
}

NOT_SURE = L("En tiedä", "Not sure", "Vet inte")

# A yes/no chip is clearer when it names the thing the question was about.
TOPIC_QUICK_REPLIES = {
    "card_details_entered": L("Kyllä, syötin korttitiedot|En, en syöttänyt korttitietoja|En ole varma",
                              "Yes, I entered my card details|No, I didn't enter card details|Not sure",
                              "Ja, jag skrev in kortuppgifterna|Nej, jag skrev inte in några kortuppgifter|Vet inte"),
    "credentials_entered": L("Kyllä, kirjauduin sivulla|En kirjautunut|En ole varma",
                             "Yes, I entered my login details|No, I didn't enter login details|Not sure",
                             "Ja, jag loggade in där|Nej, jag loggade inte in|Vet inte"),
    "code_shared": L("Kyllä, annoin koodin|En antanut koodia|En ole varma",
                     "Yes, I gave the code|No, I didn't give the code|Not sure",
                     "Ja, jag gav koden|Nej, jag gav ingen kod|Vet inte"),
    "money_transferred": L("Kyllä, rahat lähtivät|Ei, rahaa ei lähtenyt|En ole varma",
                           "Yes, the money was sent|No, no money was sent|Not sure",
                           "Ja, pengarna skickades|Nej, inga pengar skickades|Vet inte"),
    "app_installed": L("Kyllä, asensin sovelluksen|En asentanut sovellusta|En ole varma",
                       "Yes, I installed the app|No, I didn't install it|Not sure",
                       "Ja, jag installerade appen|Nej, jag installerade den inte|Vet inte"),
    "remote_access_given": L("Kyllä, annoin etäyhteyden|En antanut etäyhteyttä|En ole varma",
                             "Yes, I gave remote access|No, I didn't give remote access|Not sure",
                             "Ja, jag gav fjärråtkomst|Nej, jag gav ingen fjärråtkomst|Vet inte"),
    "payment_status": L("Kyllä, maksoin jo|En ole vielä maksanut|En ole varma",
                        "Yes, I already paid|No, I haven't paid yet|Not sure",
                        "Ja, jag har redan betalat|Nej, jag har inte betalat än|Vet inte"),
    "self_initiated": L("Kyllä, tein sen itse|En, en tehnyt sitä itse|En ole varma",
                        "Yes, I did it myself|No, I didn't do it myself|Not sure",
                        "Ja, jag gjorde det själv|Nej, jag gjorde det inte själv|Vet inte"),
}

EXPERT_LABEL = L("Puhu tietoturva-asiantuntijan kanssa", "Talk to a security expert",
                 "Prata med en säkerhetsexpert")

HANDOFF_FIELDS = {
    "fi": {"situation": "Tilanne", "checked": "Tarkistettu", "consent": "Lupa",
           "advice": "Antamani neuvo", "priority": "Kiireellisyys"},
    "en": {"situation": "Situation", "checked": "Checked", "consent": "Consent",
           "advice": "Advice given", "priority": "Priority"},
    "sv": {"situation": "Situation", "checked": "Kontrollerat", "consent": "Samtycke",
           "advice": "Rådet jag gav", "priority": "Prioritet"},
}

HANDOFF_CONFIRM = L("Tietoturva-asiantuntija ottaa sinuun yhteyttä sovelluksessa.",
                    "A security expert will contact you in the app.",
                    "En säkerhetsspecialist kontaktar dig i appen.")

# Status shown while the model-written brief is pending or cannot be produced.
# A ready brief needs no message of its own.
HANDOFF_STATUS_TEXT = {
    "pending": L("Valmistelen asiantuntijan yhteenvetoa…",
                 "Preparing the brief…",
                 "Förbereder expertens sammanfattning…"),
    "failed": L("Asiantuntijan yhteenvetoa ei voitu tuottaa.",
                "The expert brief could not be produced.",
                "Expertens sammanfattning kunde inte skapas."),
}

NEVER_ASKED = L("Salasanat, korttinumerot ja koodit.", "Passwords, card numbers and codes.",
                "Lösenord, kortnummer och koder.")

WHY_NOTE = L("Avustajan ohje, ei virallinen neuvo.",
             "Assistant guidance, not official advice.",
             "Assistentens råd, inte officiell rådgivning.")

# The corpus ships title_fi and title_en only. These are our Swedish titles:
# faithful, plain Swedish, so a Swedish "why" expander never falls back to
# English. Keyed by guidance id; a test asserts full coverage.
GUIDANCE_TITLES_SV = {
    "guidance_smishing_basics": "Att känna igen ett bedrägerimeddelande",
    "guidance_parcel_scam": "Paket- och tullavgiftsmeddelanden",
    "guidance_sender_id_spoofing": "Varför en bekant meddelandetråd inte bevisar något",
    "guidance_bank_verification": "Kontrollera ett meddelande som påstår sig komma från banken",
    "guidance_operator_impersonation": "Meddelanden och samtal i din operatörs namn",
    "guidance_family_new_number": "”Hej mamma, det här är mitt nya nummer”",
    "guidance_marketplace_scam": "Sälja online: ”köparen” skickar en betalningslänk",
    "guidance_qr_codes": "QR-koder i brev, klistermärken och parkeringslappar",
    "guidance_investment_scam": "Investeringserbjudanden med kändisar eller garanterad avkastning",
    "guidance_prompt_injection": "Meddelanden som försöker styra assistenten",
    "guidance_legitimate_notifications": "Hur ett äkta meddelande ser ut",
    "guidance_link_opened_no_input": "En länk öppnades men inget skrevs in",
    "guidance_card_details_entered": "Kortuppgifter skrevs in på en falsk sida",
    "guidance_credential_compromise": "När inloggningsuppgifter har röjts",
    "guidance_one_time_codes": "Engångskoder och PIN-koder",
    "guidance_malicious_app": "En app som installerats från en länk",
    "guidance_config_profile": "Profiler och ”certifikat” som installerats från en länk",
    "guidance_device_compromise": "När enheten inte längre går att lita på",
    "guidance_remote_access": "Förfrågningar om fjärråtkomst",
    "guidance_spam_flag_meaning": "Vad en samtalsvarning betyder",
    "guidance_bank_impostor_call": "Samtal från ”bankens säkerhetsteam”",
    "guidance_police_impostor": "Uppringare som utger sig för att vara polis",
    "guidance_tech_support_fraud": "Uppringare som erbjuder teknisk support",
    "guidance_voice_clone": "Ett brådskande samtal från en anhörig i nöd",
    "guidance_wangiri": "Missade samtal från utländska nummer",
    "guidance_sim_swap": "SIM- och eSIM-ändringar du inte har begärt",
    "guidance_esim_own_change": "En eSIM-ändring du gjorde själv",
    "guidance_number_porting": "Nummerflyttningar du inte har startat",
    "guidance_router_security": "Routrar hemma och på kontoret",
    "guidance_mfa_fatigue": "Upprepade godkännandeförfrågningar",
    "guidance_password_reset": "Byt lösenord på ett säkert sätt",
    "guidance_unrequested_reset": "Ett lösenordsåterställningsmejl du inte bad om",
    "guidance_breach_response": "Att agera på ett meddelande om dataläcka",
    "guidance_password_reuse": "Varför återanvändning gör en läcka till många",
    "guidance_fake_breach_notice": "Läckmeddelanden som själva är bedrägerier",
    "guidance_unknown_login": "Inloggning från ett land eller en enhet du inte känner igen",
    "guidance_ceo_fraud": "Betalningsförfrågningar som påstås komma från chefen",
    "guidance_invoice_fraud": "Faktura- och kontonummerbedrägerier",
    "guidance_payment_verification": "Kontrollera en betalning eller ändrade bankuppgifter",
    "guidance_shared_accounts": "Delade konton i ett litet företag",
    "guidance_offboarding": "Ta bort åtkomst när någon slutar",
    "guidance_business_email_compromise": "En företagspostlåda som någon annan kontrollerar",
    "guidance_fake_domain_invoice": "Fakturor för domäner, kataloger och register",
    "guidance_merchant_fraud": "Bedrägerier med betalterminaler och handlarportaler",
    "guidance_order_confirmations": "Oväntade orderbekräftelser på ett företagskonto",
    "guidance_malicious_attachment": "Oväntade bilagor: fakturor, reklamationer och ansökningar",
    "guidance_data_protection_breach": "När kunders personuppgifter kan ha läckt",
    "guidance_ransomware": "Filer som plötsligt har krypterats",
    "guidance_report_to_police": "Att anmäla ett bedrägeri",
    "guidance_monitoring_apps": "Om du tror att någon nära övervakar din telefon",
    "guidance_asking_for_evidence": "Att be användaren om mer information",
    "guidance_handing_off": "När en människa ska ta över",
    "guidance_proportionate_advice": "Proportionalitet",
    "guidance_privacy_consent": "Användning av valfria konto- och enhetsuppgifter",
    "guidance_out_of_scope": "Förfrågningar som en säkerhetsassistent ska avböja",
}

LINK_CHECK_TEXT = {
    "warn": L("Linkkitarkistus: epäilyttävä linkki", "Link check: suspicious link",
              "Länkkontroll: misstänkt länk"),
    "ok": L("Linkkitarkistus: ei merkkejä huijauksesta", "Link check: no signs of a scam",
            "Länkkontroll: inga tecken på bedrägeri"),
    "unknown": L("Linkkitarkistus: ei varmaa tulosta", "Link check: no clear result",
                 "Länkkontroll: inget säkert resultat"),
}

CALL_WARNING_TEXT = {
    "suspected_scam": ("warn", L("Puheluvaroitus: numero on merkitty huijaussoitoksi",
                                 "Call warning: the number is marked as a scam",
                                 "Samtalsvarning: numret är markerat som bedrägeri")),
    "possible_spam": ("warn", L("Puheluvaroitus: numero on merkitty mahdolliseksi roskapuheluksi",
                                "Call warning: the number is marked as possible spam",
                                "Samtalsvarning: numret är markerat som möjligt spamsamtal")),
    "spoofed_caller_id": ("warn", L("Puheluvaroitus: soittajan numero voi olla väärennetty",
                                    "Call warning: the caller's number may be faked",
                                    "Samtalsvarning: numret kan vara förfalskat")),
    "suspected_premium_rate": ("warn", L("Puheluvaroitus: numero saattaa olla kallis lisämaksunumero",
                                         "Call warning: the number may be an expensive premium number",
                                         "Samtalsvarning: numret kan vara ett dyrt betalnummer")),
    "none": ("ok", L("Puheluvaroitus: numerosta ei ole merkintöjä",
                     "Call warning: no warnings for this number",
                     "Samtalsvarning: inga varningar för numret")),
}

_SAID = L('Kerroit: "%s"', 'You said: "%s"', 'Du sa: "%s"')
_USED_WITH_CONSENT = L("Katsoin luvallasi: %s.", "With your permission, I checked: %s.",
                       "Med ditt tillstånd kollade jag: %s.")
_CHECKED_MESSAGE = L("Luin lähettämäsi viestin.",
                     "I read the message you shared.",
                     "Jag läste meddelandet du delade.")
_BASIS_ONLY = L("Arvio perustuu vain tässä keskustelussa kertomiisi tietoihin.",
                "This assessment uses only what you told me in this conversation.",
                "Bedömningen bygger bara på det du berättat i den här konversationen.")
_NO_GATED = L("Ei lupaa vaativia tietoja.", "No details that need permission.",
              "Inga uppgifter som kräver tillstånd.")
_NO_PERMISSION = L("Ei lupaa vaativia tietoja käytössä.",
                   "No details that need permission were used.",
                   "Inga uppgifter som kräver tillstånd användes.")
_NO_CONSENT_ANSWER = L("Lupapyyntöön ei ole vielä vastattu.",
                       "The permission request is not answered yet.",
                       "Tillståndsförfrågan är ännu inte besvarad.")
_SHARED_DESCRIPTION = L("Kuvauksesi tilanteesta", "Your description of the situation",
                        "Din beskrivning av situationen")
_FROM = L("%s lähettäjältä %s", "%s from %s", "%s från %s")
_STILL_UNKNOWN = L("Vielä selvittämättä: %s.", "Still unknown: %s.", "Ännu oklart: %s.")
_FIRST_STEP = L("Asiantuntijan ensimmäinen askel: %s.", "Expert's first step: %s.",
                "Expertens första steg: %s.")

_AGE_TODAY = L("sivusto luotu tänään", "site created today", "webbplatsen skapades i dag")
_AGE_YESTERDAY = L("sivusto luotu eilen", "site created yesterday", "webbplatsen skapades i går")
_AGE_DAYS = L("sivusto luotu %d päivää sitten", "site created %d days ago",
              "webbplatsen skapades för %d dagar sedan")
_AGE_YEAR = L("sivusto on ollut olemassa yli vuoden", "site has existed for over a year",
              "webbplatsen har funnits i över ett år")

_URL = re.compile(r"https?://[^\s<>\"')]+", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _guidance_titles():
    """id -> {fi, en, sv}. Swedish comes from our own table, not a fallback."""
    out = {}
    try:
        with open(GUIDANCE_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                gid = row.get("id")
                en = row.get("title_en") or row.get("title_fi") or ""
                title = L(row.get("title_fi") or en, en, "")
                title["sv"] = GUIDANCE_TITLES_SV.get(gid) or title["en"]
                out[gid] = title
    except (OSError, ValueError):
        return {}
    return out


_GUIDANCE_TITLES = _guidance_titles()


# --- small formatters -------------------------------------------------------


def consent_tokens(case):
    """{signal path: opaque token} in the case's own consent order."""
    consent = (case or {}).get("consent") or {}
    paths = [p for p in consent.get("requires_consent") or [] if isinstance(p, str)]
    return {path: "s%d" % (i + 1) for i, path in enumerate(paths)}


def resolve_fields(case, values):
    """Map tokens or paths from a consent answer back to signal paths."""
    tokens = consent_tokens(case)
    allowed = set(tokens)
    out = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        path = value if value in allowed else None
        if path is None:
            for candidate, token in tokens.items():
                if token == value:
                    path = candidate
                    break
        if path and path not in out:
            out.append(path)
    return out


def attachment(case, lang):
    """The forwarded item as plain text, plus the checks we ran on it."""
    signals = (case or {}).get("signals") or {}
    artifact = signals.get("artifact")
    if not isinstance(artifact, dict):
        return None
    kind = _ARTIFACT_KIND.get(artifact.get("type"), "notification")
    return {
        "kind": kind,
        "kind_label": _pick(ATTACHMENT_KINDS.get(kind, ATTACHMENT_KINDS["notification"]), lang),
        "sender": _clip(artifact.get("sender"), 200),
        "time": _clock(artifact.get("received_at")),
        "body": _clip(artifact.get("body"), 4000),
        "checks": checks(case, lang),
    }


def _clock(value):
    """HH:MM from an ISO timestamp, or None when it cannot be read."""
    text = _s(value)
    if not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        return None


def _age_phrase(days, lang):
    try:
        days = int(days)
    except (TypeError, ValueError):
        return ""
    if days < 0:
        return ""
    if days == 0:
        return _pick(_AGE_TODAY, lang)
    if days == 1:
        return _pick(_AGE_YESTERDAY, lang)
    if days >= 365:
        return _pick(_AGE_YEAR, lang)
    return _pick(_AGE_DAYS, lang) % days


def checks(case, lang):
    """Link and call checks as tone + localised line. No ids, no confidence."""
    signals = (case or {}).get("signals") or {}
    rows = []
    link = signals.get("link_check")
    if isinstance(link, dict):
        verdict = link.get("verdict")
        tone = "warn" if verdict in ("malicious", "suspicious") else (
            "ok" if verdict == "clean" else "unknown")
        text = _pick(LINK_CHECK_TEXT[tone], lang)
        age = _age_phrase(link.get("domain_age_days"), lang)
        if age:
            text = "%s · %s" % (text, age)
        rows.append({"tone": tone, "text": text})
    call = signals.get("call_warning")
    if isinstance(call, dict):
        warning = call.get("warning")
        if warning in CALL_WARNING_TEXT:
            tone, text = CALL_WARNING_TEXT[warning]
        else:
            tone = "unknown"
            text = L("Puheluvaroitus: ei osaa sanoa", "Call warning: can't say",
                     "Samtalsvarning: kan inte avgöra")
        rows.append({"tone": tone, "text": _pick(text, lang)})
    return rows


# --- why / steps ------------------------------------------------------------


def _sentences(text):
    return [s.strip() for s in _SENTENCE.split(_s(text)) if s.strip()]


def _reason(advice):
    """First sentence when it fits, otherwise the first 200 characters."""
    text = " ".join(_s(advice).split())
    if not text:
        return ""
    first = _sentences(text)[0]
    if len(first) <= 200:
        return first
    cut = text[:200]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:.-") + "…"


def _steps(answer, advice):
    steps = [s.strip() for s in (answer.get("steps") or []) if isinstance(s, str) and s.strip()]
    if steps:
        return steps[:5]
    return _sentences(advice)[1:6]


def _normalise(text):
    return " ".join(re.sub(r"\W+", " ", _s(text).lower()).split())


def _overlaps(sentence, others):
    """Whether a sentence is already the reason or covered by a step.

    A loose match on purpose: a near-duplicate reads badly, but dropping a
    safety instruction because it paraphrases a step would be worse.
    """
    text = _normalise(sentence)
    if not text:
        return True
    words = set(text.split())
    for other in others:
        other_text = _normalise(other)
        if not other_text:
            continue
        if text == other_text:
            return True
        if len(text) >= 20 and len(other_text) >= 20 and (
                text in other_text or other_text in text):
            return True
        other_words = set(other_text.split())
        if other_words and len(words & other_words) / float(len(words)) >= 0.85:
            return True
    return False


def _more(advice, reason, steps):
    """Advice sentences the answer card would otherwise drop.

    The reason is the first sentence and the steps come from the answer, so
    only the remaining sentences belong here.
    """
    covered = [reason] + list(steps)
    return [s for s in _sentences(advice)[1:] if not _overlaps(s, covered)]


def _urgency(answer):
    urgency = answer.get("urgency")
    if urgency in URGENCIES:
        return urgency
    return {"none": "none", "low": "routine", "medium": "today",
            "high": "today", "critical": "immediate"}.get(answer.get("risk_level"), "today")


def _allowed(case, state, path):
    """Whether this signal may honestly be described as used."""
    consent = (case or {}).get("consent") or {}
    if path not in (consent.get("requires_consent") or []):
        return True
    allowed = set(consent.get("pre_granted") or []) | set(state.get("granted") or [])
    return path in allowed


def _why(case, state, answer, lang):
    bullets = []
    facts = state.get("facts") if isinstance(state.get("facts"), dict) else {}
    for text in facts.values():
        quote = _clip(text, 150)
        if quote:
            bullets.append(_pick(_SAID, lang) % quote)
        if len(bullets) >= 2:
            break

    for row in checks(case, lang):
        bullets.append(row["text"])

    sensitive = set(((case or {}).get("consent") or {}).get("requires_consent") or [])
    used = [s for s in answer.get("signals_used") or [] if isinstance(s, str)]
    for path in used:
        if path in sensitive and path in SIGNALS and _allowed(case, state, path):
            bullets.append(_pick(_USED_WITH_CONSENT, lang) % _pick(SIGNALS[path], lang).lower())

    curated = []
    for bullet in bullets:
        if bullet not in curated:
            curated.append(bullet)
    curated = curated[:4]
    if len(curated) < 2 and (case or {}).get("signals", {}).get("artifact"):
        curated.append(_pick(_CHECKED_MESSAGE, lang))
    if len(curated) < 2:
        curated.append(_pick(_BASIS_ONLY, lang))

    sources = []
    for gid in answer.get("citations") or []:
        title = _GUIDANCE_TITLES.get(gid)
        if title:
            name = _pick(title, lang)
            if name and name not in sources:
                sources.append(name)
    return {"bullets": curated, "sources": sources[:3], "note": _pick(WHY_NOTE, lang)}


# --- blocks -----------------------------------------------------------------


def _is_yes_no(text, lang):
    pattern = _YES_NO.get(lang)
    return bool(pattern and pattern.match(_s(text)))


def quick_replies(reply, lang):
    """Chips that fit the question. A closed yes/no question gets topic chips
    for the topic it names; an open question gets one honest fallback."""
    if not _is_yes_no(reply.get("text"), lang):
        return [_pick(NOT_SURE, lang)]
    topics = [t for t in (reply.get("topics") or []) if isinstance(t, str)]
    for topic in topics:
        table = TOPIC_QUICK_REPLIES.get(topic)
        if table:
            parts = _pick(table, lang).split("|")
            if len(parts) == 3:
                return parts
    return list(QUICK_REPLIES.get(lang, QUICK_REPLIES["en"]))


def consent(case, reply, lang):
    tokens = consent_tokens(case)
    fields = [f for f in (reply.get("fields") or []) if isinstance(f, str) and f in tokens]
    if not fields:
        return None
    items = [{"field": tokens[path], "label": _pick(CONSENT[path]["label"], lang)}
             for path in fields if path in CONSENT]
    purposes = [_pick(CONSENT[path]["purpose"], lang) for path in fields if path in CONSENT]
    if len(fields) == 1 and fields[0] in CONSENT:
        # One item: the title names it, like the mockup's "May I check your
        # recent sign-ins?". Several items: the generic title.
        title = _pick(CONSENT[fields[0]]["question"], lang)
    else:
        title = _pick(CONSENT_TITLE, lang)
    return {
        "fields": [tokens[path] for path in fields],
        "title": title,
        "purpose": " ".join(purposes),
        "items": items,
        "allow": _pick(CONSENT_ALLOW, lang),
        "deny": _pick(CONSENT_DENY, lang),
        "fine": _pick(CONSENT_FINE, lang),
    }


def visibility(case, state, lang):
    """What I can see: shared, checked, granted, refused, never asked for."""
    case = case if isinstance(case, dict) else {}
    state = state if isinstance(state, dict) else {}
    att = attachment(case, lang)
    if att:
        if att["sender"]:
            line = _pick(_FROM, lang) % (att["kind_label"], att["sender"])
        else:
            line = att["kind_label"]
        if att["time"]:
            line = "%s · %s" % (line, att["time"])
        shared = [line]
    else:
        shared = [_pick(_SHARED_DESCRIPTION, lang)]

    granted = [_pick(SIGNALS[path], lang) for path in (state.get("granted") or [])
               if path in SIGNALS]
    refused = [_pick(SIGNALS[path], lang) for path in (state.get("refused") or [])
               if path in SIGNALS]
    return {
        "shared": shared,
        "checked": [row["text"] for row in checks(case, lang)],
        "granted": granted,
        "refused": refused,
        "never": _pick(NEVER_ASKED, lang),
    }


def answer_block(case, state, answer, lang, fallback=False):
    action = answer.get("primary_action")
    urgency = _urgency(answer)
    advice = _s(answer.get("advice_text"))
    reason = _reason(advice)
    steps = _steps(answer, advice)
    return {
        "urgency": urgency,
        "urgency_label": _pick(URGENCY_LABELS[urgency], lang),
        "headline": _pick(ACTIONS.get(action, ACTIONS["verify_via_official_channel"]), lang),
        "reason": reason,
        "steps": steps,
        "more": _more(advice, reason, steps),
        "escalate": bool(answer.get("escalation_required")),
        "expert_label": _pick(EXPERT_LABEL, lang),
        "fallback": bool(fallback),
        "why": _why(case, state, answer, lang),
    }


def _target_label(case, answer, lang):
    target = answer.get("escalation_target")
    if target not in ESCALATION_TARGETS:
        target = ("business_security_support" if case.get("audience") == "small_business"
                  else "security_specialist")
    return _pick(ESCALATION_TARGETS[target], lang)


def _line(template, text, lang):
    """Fill a sentence template that ends in a full stop, without doubling it."""
    text = _s(text)
    out = _pick(template, lang) % text
    if text.endswith((".", "!", "?", "…")) and out.endswith("."):
        out = out[:-1]
    return out


def _str_items(value):
    return [v.strip() for v in value if _s(v)] if isinstance(value, list) else []


def _join(items):
    """Join brief items without stacking a semicolon on a finished sentence."""
    out = ""
    for item in items:
        if not out:
            out = item
        elif out.endswith((".", "?", "!", "…")):
            out = "%s %s" % (out, item)
        else:
            out = "%s; %s" % (out, item)
    return out


def _same_action(first, other):
    """True when two brief phrases say the same thing after cleaning."""
    def clean(text):
        return re.sub(r"[\W_]+", "", _s(text).lower())

    first, other = clean(first), clean(other)
    if not first or not other:
        return False
    return first in other or other in first


def brief_priority(brief):
    """The model's validated escalation priority, or None.

    Only a JSON integer from 1 to 5 is a level. `bool` is an int subclass in
    Python, so it is rejected explicitly.
    """
    value = brief.get("escalation_priority") if isinstance(brief, dict) else None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= 5 else None


def valid_brief(brief):
    """Whether there is enough validated model output to show a handoff card."""
    return (isinstance(brief, dict) and bool(_s(brief.get("situation")))
            and bool(_s(brief.get("first_action")))
            and brief_priority(brief) is not None)


def handoff_status_text(status, lang):
    """The localised line for a pending or failed brief; None otherwise."""
    return _pick(HANDOFF_STATUS_TEXT[status], lang) if status in HANDOFF_STATUS_TEXT else None


def handoff_status(state, lang):
    """pending/ready/failed for the handoff card. A ready brief has no message."""
    status = state.get("handoff_status")
    if status not in ("pending", "ready", "failed"):
        status = "ready" if valid_brief(state.get("handoff_brief")) else "failed"
    elif status == "ready" and not valid_brief(state.get("handoff_brief")):
        status = "failed"
    return {"status": status, "text": handoff_status_text(status, lang)}


def _handoff_consent(case, state, lang):
    """Granted and refused labels. Never the model's own consent claims."""
    granted = [path for path in (state.get("granted") or []) if path in SIGNALS]
    refused = [path for path in (state.get("refused") or []) if path in SIGNALS]
    asked = [path for path in (state.get("consent_asked") or []) if path in CONSENT]
    if granted or refused:
        parts = []
        if granted:
            parts.append(_pick(L("Myönsit: %s.", "You allowed: %s.", "Du tillät: %s."), lang) % ", ".join(
                _pick(SIGNALS[p], lang) for p in granted))
        if refused:
            parts.append(_pick(L("Kieltäydyit: %s.", "You refused: %s.", "Du nekade: %s."), lang) % ", ".join(
                _pick(SIGNALS[p], lang) for p in refused))
        return _clip(" ".join(parts), 400)
    if asked:
        return _clip(_pick(_NO_CONSENT_ANSWER, lang), 400)
    if ((case.get("consent") or {}).get("requires_consent") or []):
        return _clip(_pick(_NO_PERMISSION, lang), 400)
    return _clip(_pick(_NO_GATED, lang), 400)


def handoff(case, state, answer, lang):
    """The model-written brief mapped for the handoff card, or None.

    There is no deterministic substitute: without valid model output the UI
    gets a status instead of a made-up summary.
    """
    if state.get("handoff_status") in ("pending", "failed"):
        return None
    brief = state.get("handoff_brief")
    if not valid_brief(brief):
        return None
    target = _target_label(case, answer, lang)
    consent_text = _handoff_consent(case, state, lang)
    labels = dict(HANDOFF_FIELDS.get(lang, HANDOFF_FIELDS["en"]))
    confirm = _pick(HANDOFF_CONFIRM, lang)
    urgency = _urgency(answer)

    # The situation is the one model-written summary and is meant to be
    # self-contained, so appending user_actions here would say it twice. They
    # stay structured in `brief` for the expert, not stitched into prose.
    situation = _clip(brief["situation"], 400)
    questions = _str_items(brief.get("open_questions"))
    if questions:
        situation = "%s %s" % (
            situation, _line(_STILL_UNKNOWN, _clip(_join(questions), 90), lang))
    # Evidence is the model's own list. An empty list stays empty: the case
    # must not be mined for facts the brief did not assert.
    evidence = _str_items(brief.get("evidence"))
    checked = _clip(_join(evidence), 400) if evidence else ""
    advice = _line(_FIRST_STEP, brief["first_action"], lang)
    given = _str_items(brief.get("advice_given"))
    if given and _same_action(brief["first_action"], given[0]):
        given = given[1:]
    if given:
        advice = "%s %s" % (advice, _join(given))
    priority = brief.get("priority")
    if priority not in URGENCY_LABELS:
        priority = urgency
    return {
        "target_label": target,
        "situation": _clip(situation, 400),
        "checked": checked,
        "consent": consent_text,
        "advice": _clip(advice, 400),
        "priority": _pick(URGENCY_LABELS[priority], lang),
        "labels": labels,
        "confirm": confirm,
        "brief": brief,
    }


def display(case, state, reply, language):
    """The whole `display` block for one reply. Cheap, pure and localised."""
    lang = language if language in LANGUAGES else "fi"
    case = case if isinstance(case, dict) else {}
    state = state if isinstance(state, dict) else {}
    reply = reply if isinstance(reply, dict) else {}
    rtype = reply.get("type")
    answer = reply.get("answer") if isinstance(reply.get("answer"), dict) else None

    out = {
        "attachment": attachment(case, lang),
        "question": None,
        "quick_replies": None,
        "consent": None,
        "answer": None,
        "handoff": None,
        "handoff_status": None,
        "visibility": visibility(case, state, lang),
    }
    if rtype == "question":
        text = _s(reply.get("text"))
        if text:
            out["question"] = {"text": text}
            out["quick_replies"] = quick_replies(reply, lang)
    elif rtype == "consent_request":
        out["consent"] = consent(case, reply, lang)
    elif rtype == "notice":
        # A closed chat gets a courtesy line only: no answer, no handoff.
        text = _s(reply.get("text"))
        if text:
            out["notice"] = {"text": text}
    if rtype == "final" and answer:
        out["answer"] = answer_block(case, state, answer, lang, reply.get("fallback"))
        if answer.get("escalation_required"):
            out["handoff"] = handoff(case, state, answer, lang)
            out["handoff_status"] = handoff_status(state, lang)
    return out


def artifact_from_attachment(kind, sender, body, language):
    """Build a pieces.artifact dict from the demo's attachment sheet.

    The kind is chosen by the user, the text is untrusted. No links are
    fetched and no link check is invented.
    """
    lang = language if language in LANGUAGES else "fi"
    return {
        "type": kind,
        "channel_language": lang,
        "sender": _clip(sender, 200),
        "body": _s(body)[:4000],
        "links": _URL.findall(_s(body))[:10],
        "received_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
