"""One flow per rail, picked by alert.rail (D2). The engine (checks, rules) is shared; flows own the
deadlines, the next-step menu and rail-only sections such as UK reimbursement facts."""

from types import ModuleType

from investigator.schema import Rail


def flow_for(rail: Rail) -> ModuleType:
    from investigator.flows import sepa_inst, uk_fps
    return {Rail.FPS: uk_fps, Rail.SEPA_INST: sepa_inst}[rail]
