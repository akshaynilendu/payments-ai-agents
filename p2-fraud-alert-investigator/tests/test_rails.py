from investigator.schema import SepaCaseSummary, SepaNextStep, UkCaseSummary, UkNextStep


def test_flow_follows_the_rail(ds, summaries):
    for a in ds.alerts:
        expected = UkCaseSummary if a.rail == "FPS" else SepaCaseSummary
        assert type(summaries[a.alert_id]) is expected


def test_uk_summaries_have_no_sepa_fields_and_vice_versa(summaries):
    for s in summaries.values():
        d = s.model_dump()
        if isinstance(s, UkCaseSummary):
            assert "deadline_note" not in d["alert"]
            assert d["alert"]["decide_suspicion_by"] and d["alert"]["execute_or_refuse_by"]
            assert d["alert"]["name_check_label"] == "Confirmation of Payee"
            assert "reimbursement" in d
        else:
            assert d["alert"]["decide_suspicion_by"] is None and d["alert"]["execute_or_refuse_by"] is None
            assert d["alert"]["deadline_note"] == "Held before execution; no regulated hold window; not sent until decided"
            assert d["alert"]["name_check_label"] == "Verification of Payee"
            assert "reimbursement" not in d and "received_on_business_day" not in d["alert"]


def test_name_check_wording_never_crosses_rails(summaries):
    for s in summaries.values():
        text = s.model_dump_json()
        wrong = "Verification of Payee" if isinstance(s, UkCaseSummary) else "Confirmation of Payee"
        assert wrong not in text


def test_menus_are_rail_specific():
    assert {s.value for s in UkNextStep} == {"RELEASE_WITH_NOTE", "CALL_CUSTOMER_REGISTERED_NUMBER",
                                              "ASK_PAYMENT_PURPOSE", "REQUEST_INFO_RECEIVING_BANK", "ESCALATE_MLRO"}
    assert {s.value for s in SepaNextStep} == {"EXECUTE_WITH_NOTE", "REJECT_BEFORE_EXECUTION",
                                                "CALL_CUSTOMER_REGISTERED_NUMBER", "ASK_PAYMENT_PURPOSE", "ESCALATE_MLRO"}
    assert not any("RECALL" in s.value for s in list(UkNextStep) + list(SepaNextStep))


def test_steps_come_from_the_right_menu(summaries):
    for s in summaries.values():
        menu = UkNextStep if isinstance(s, UkCaseSummary) else SepaNextStep
        assert all(isinstance(n.step, menu) for n in s.next_steps)
