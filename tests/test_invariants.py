"""The bridge to pryti-semantic-reviewer: contract -> confirmed invariant corpus."""
from pryti_contract import build
from pryti_contract.invariants import _declared_destinations, to_invariant_corpus
from pryti_contract.models import Contract, Route


def _contract_with(*effects):
    c = Contract()
    c.add_route(Route(method="POST", path="/orders", handler="views.create_order",
                      auth="user", effects=sorted(effects), source="declared"))
    return c


def test_declared_destinations_strips_net_prefix_and_locals():
    c = _contract_with("net:api.stripe.com", "net:localhost", "email")
    assert _declared_destinations(c) == ["api.stripe.com"]


def test_corpus_has_the_three_confirmed_invariants():
    corpus = to_invariant_corpus(_contract_with("net:api.stripe.com"))
    ids = {inv["id"] for inv in corpus}
    assert ids == {"external-egress-allowlist", "auth-before-write", "pii-egress-authed"}
    assert all(inv["confirmed"] for inv in corpus)


def test_allowlist_carries_the_declared_destinations():
    corpus = to_invariant_corpus(_contract_with("net:api.stripe.com", "net:api.twilio.com"))
    allow = next(i for i in corpus if i["id"] == "external-egress-allowlist")
    assert allow["observed"]["destinations"] == ["api.stripe.com", "api.twilio.com"]
    assert allow["severity"] == "critical"


def test_corpus_is_json_serialisable_shape():
    import json

    corpus = to_invariant_corpus(build(include_django=False))
    # every entry must carry the fields the reviewer's enforce() reads
    for inv in json.loads(json.dumps(corpus)):
        assert inv["id"] and inv["statement"] and inv["confirmed"] is True
