"""Regression tests for Stripe Event object access in the webhook handler."""

import stripe


def test_stripe_event_uses_attribute_access_for_event_metadata():
    event = stripe.Event.construct_from(
        {
            "id": "evt_test",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test"}},
        },
        "acct_test",
    )

    # stripe.Event is an object, not a dict. This was the source of the
    # production AttributeError: 'Event' object has no attribute 'get'.
    assert not hasattr(event, "get")
    assert event.id == "evt_test"
    assert event.type == "checkout.session.completed"


def test_stripe_event_data_shape_supports_webhook_handlers():
    event = stripe.Event.construct_from(
        {
            "id": "evt_test",
            "type": "customer.subscription.updated",
            "data": {
                "object": {"customer": "cus_test"},
                "previous_attributes": {"status": "trialing"},
            },
        },
        "acct_test",
    )

    assert event.data.object["customer"] == "cus_test"
    assert event.data.previous_attributes is not None
    assert event.data.previous_attributes["status"] == "trialing"
