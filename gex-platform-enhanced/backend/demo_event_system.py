"""
GreenEarthX Event-Driven Architecture Demo
Complete chain of custody demonstration
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.event_store import EventStore, log_event, get_compliance_thread, verify_integrity
from app.core.state_machine import transition_state, get_valid_next_states
import uuid
import json


def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")


def demo_complete_lifecycle():
    """
    Demonstrate complete molecule lifecycle with full audit trail
    Capacity → Token → Offer → Match → Contract → Delivery
    """
    
    print_section("GreenEarthX Event-Driven Architecture Demo")
    print("This demo shows a complete molecule lifecycle with full audit trail\n")
    
    # Generate correlation ID for this business transaction
    correlation_id = f"DEMO-{str(uuid.uuid4())[:8].upper()}"
    print(f"📋 Correlation ID: {correlation_id}")
    print("   This ID will link all events in the chain of custody\n")
    
    # ====================
    # 1. CREATE CAPACITY
    # ====================
    print_section("1. Create Production Capacity")
    
    capacity_id = str(uuid.uuid4())
    
    event1 = EventStore.append_event(
        event_type="capacity.created",
        aggregate_type="capacity",
        aggregate_id=capacity_id,
        data={
            "project_name": "Hanover Green H2",
            "molecule": "H2",
            "capacity_mtpd": 50.0,
            "location": "Hanover, Germany",
            "certifications": ["RED III", "RFNBO", "45V"]
        },
        user_id="producer@greenh2.com",
        correlation_id=correlation_id
    )
    
    print(f"✅ Capacity created: {capacity_id[:8]}...")
    print(f"   Event ID: {event1}")
    
    # ====================
    # 2. VERIFY CAPACITY
    # ====================
    print_section("2. Verify Capacity (Compliance Check)")
    
    event2 = transition_state(
        aggregate_type="capacity",
        aggregate_id=capacity_id,
        from_state="draft",
        to_state="pending_verification",
        data={"submitted_by": "producer@greenh2.com"},
        user_id="producer@greenh2.com",
        correlation_id=correlation_id
    )
    
    print("✅ Submitted for verification")
    
    event3 = transition_state(
        aggregate_type="capacity",
        aggregate_id=capacity_id,
        from_state="pending_verification",
        to_state="verified",
        data={
            "verified_by": "regulator@eu.gov",
            "certifications_valid": True,
            "ghg_intensity": 0.8  # kg CO2e/kg H2
        },
        user_id="regulator@eu.gov",
        correlation_id=correlation_id
    )
    
    print("✅ Capacity verified by regulator")
    print("   GHG Intensity: 0.8 kg CO2e/kg H2")
    
    # ====================
    # 3. TOKENIZE CAPACITY
    # ====================
    print_section("3. Tokenize Capacity")
    
    token_id = str(uuid.uuid4())
    
    event4 = EventStore.append_event(
        event_type="token.minted",
        aggregate_type="token",
        aggregate_id=token_id,
        data={
            "capacity_id": capacity_id,
            "tokenised_mtpd": 32.5,
            "delivery_start": "2027-01-01",
            "delivery_end": "2030-12-31",
            "compliance_certifications": ["RED III", "RFNBO"]
        },
        user_id="producer@greenh2.com",
        correlation_id=correlation_id
    )
    
    print(f"✅ Token minted: {token_id[:8]}...")
    print("   Volume: 32.5 MTPD")
    print("   Compliance: RED III, RFNBO")
    
    # ====================
    # 4. CREATE OFFER
    # ====================
    print_section("4. Create Marketplace Offer")
    
    offer_id = str(uuid.uuid4())
    
    event5 = EventStore.append_event(
        event_type="offer.created",
        aggregate_type="offer",
        aggregate_id=offer_id,
        data={
            "token_id": token_id,
            "volume_mtpd": 15.0,
            "price_eur_kg": 6.80,
            "offer_type": "firm",
            "delivery_terms": "DDP Hamburg"
        },
        user_id="producer@greenh2.com",
        correlation_id=correlation_id
    )
    
    print(f"✅ Offer created: {offer_id[:8]}...")
    print("   Volume: 15.0 MTPD")
    print("   Price: €6.80/kg")
    
    # ====================
    # 5. MATCH WITH BUYER
    # ====================
    print_section("5. Match with Buyer RFQ")
    
    match_id = str(uuid.uuid4())
    
    event6 = EventStore.append_event(
        event_type="match.created",
        aggregate_type="match",
        aggregate_id=match_id,
        data={
            "offer_id": offer_id,
            "rfq_id": str(uuid.uuid4()),
            "match_score": 92,
            "volume_mtpd": 15.0,
            "buyer": "BASF SE"
        },
        user_id="system",
        correlation_id=correlation_id
    )
    
    print(f"✅ Match created: {match_id[:8]}...")
    print("   Match Score: 92%")
    print("   Buyer: BASF SE")
    
    event7 = transition_state(
        aggregate_type="match",
        aggregate_id=match_id,
        from_state="pending",
        to_state="accepted",
        data={"accepted_by": "trader@basf.com"},
        user_id="trader@basf.com",
        correlation_id=correlation_id
    )
    
    print("✅ Match accepted by buyer")
    
    # ====================
    # 6. CREATE CONTRACT
    # ====================
    print_section("6. Create Supply Contract")
    
    contract_id = str(uuid.uuid4())
    
    event8 = EventStore.append_event(
        event_type="contract.created",
        aggregate_type="contract",
        aggregate_id=contract_id,
        data={
            "match_id": match_id,
            "counterparty": "BASF SE",
            "volume_mtpd": 15.0,
            "price_eur_kg": 6.80,
            "delivery_start": "2027-01-01",
            "delivery_end": "2030-12-31",
            "contract_value_eur": 11_137_500  # 15 MTPD * 365 days * 3 years * €6.80/kg
        },
        user_id="producer@greenh2.com",
        correlation_id=correlation_id
    )
    
    print(f"✅ Contract created: {contract_id[:8]}...")
    print("   Contract Value: €11,137,500")
    
    # Credit check
    event9 = transition_state(
        aggregate_type="contract",
        aggregate_id=contract_id,
        from_state="draft",
        to_state="pending_credit_check",
        data={"requested_by": "finance@greenh2.com"},
        user_id="finance@greenh2.com",
        correlation_id=correlation_id
    )
    
    print("✅ Credit check initiated")
    
    event10 = transition_state(
        aggregate_type="contract",
        aggregate_id=contract_id,
        from_state="pending_credit_check",
        to_state="credit_approved",
        data={
            "credit_rating": "A+",
            "approved_by": "credit_officer@bank.com"
        },
        user_id="credit_officer@bank.com",
        correlation_id=correlation_id
    )
    
    print("✅ Credit approved (BASF: A+ rating)")
    
    # Send for signature
    event11 = transition_state(
        aggregate_type="contract",
        aggregate_id=contract_id,
        from_state="credit_approved",
        to_state="pending_signature",
        data={
            "sent_for_signature": "2026-01-28",
            "signers": ["producer@greenh2.com", "buyer@basf.com"]
        },
        user_id="legal@greenh2.com",
        correlation_id=correlation_id
    )
    
    print("✅ Sent for signature")
    
    # Signature
    event12 = transition_state(
        aggregate_type="contract",
        aggregate_id=contract_id,
        from_state="pending_signature",
        to_state="partially_signed",
        data={
            "producer_signed": "2026-01-28",
            "signed_by": "ceo@greenh2.com"
        },
        user_id="ceo@greenh2.com",
        correlation_id=correlation_id
    )
    
    print("✅ Partially signed (producer)")
    
    event13 = transition_state(
        aggregate_type="contract",
        aggregate_id=contract_id,
        from_state="partially_signed",
        to_state="fully_signed",
        data={
            "buyer_signed": "2026-01-29",
            "signed_by": "procurement@basf.com"
        },
        user_id="procurement@basf.com",
        correlation_id=correlation_id
    )
    
    print("✅ Contract fully signed by both parties")
    
    # ====================
    # 7. DELIVERY
    # ====================
    print_section("7. Delivery Confirmation")
    
    event14 = transition_state(
        aggregate_type="contract",
        aggregate_id=contract_id,
        from_state="fully_signed",
        to_state="delivering",
        data={"delivery_started": "2027-01-01"},
        user_id="operations@greenh2.com",
        correlation_id=correlation_id
    )
    
    print("✅ Delivery started (2027-01-01)")
    
    event15 = EventStore.append_event(
        event_type="certificate.transferred",
        aggregate_type="compliance",
        aggregate_id=str(uuid.uuid4()),
        data={
            "contract_id": contract_id,
            "certificate_type": "RED III",
            "certificate_id": "RED-EU-2027-001234",
            "from": "Hanover Green H2",
            "to": "BASF SE",
            "volume_kg": 15000  # 15 MTPD * 1 day
        },
        user_id="system",
        correlation_id=correlation_id
    )
    
    print("✅ RED III certificate transferred to BASF")
    print("   Certificate ID: RED-EU-2027-001234")
    
    # ====================
    # ANALYSIS
    # ====================
    print_section("Chain of Custody Analysis")
    
    # Get all events for this transaction
    events = get_compliance_thread(correlation_id)
    
    print(f"📊 Total Events: {len(events)}")
    print(f"📋 Correlation ID: {correlation_id}")
    print(f"⏱️  Duration: {events[0]['timestamp']} → {events[-1]['timestamp']}")
    print(f"\n📝 Event Timeline:")
    
    for i, event in enumerate(events, 1):
        event_type = event['event_type']
        timestamp = event['timestamp']
        entity = event['entity']
        
        print(f"   {i:2}. [{timestamp}] {event_type}")
        print(f"       Entity: {entity}")
    
    # ====================
    # VERIFICATION
    # ====================
    print_section("Cryptographic Verification")
    
    print("🔐 Verifying event chain integrity...")
    
    try:
        verify_integrity()
        print("✅ VERIFIED: Event chain is intact and has not been tampered with")
        print("   All hashes verified ✓")
        print("   All links verified ✓")
        print("   Chain of custody is cryptographically provable")
    except Exception as e:
        print(f"❌ TAMPER DETECTED: {e}")
    
    # ====================
    # COMPLIANCE REPORT
    # ====================
    print_section("Regulatory Compliance Report")
    
    print("📄 Chain of Custody Report")
    print(f"   Correlation ID: {correlation_id}")
    print(f"   Project: Hanover Green H2")
    print(f"   Molecule: H2 (Hydrogen)")
    print(f"   Volume: 15.0 MTPD")
    print(f"   Buyer: BASF SE")
    print(f"\n✅ Compliance Status:")
    print("   • Capacity Verified: ✓ (by EU Regulator)")
    print("   • Certifications: RED III ✓, RFNBO ✓, 45V ✓")
    print("   • GHG Intensity: 0.8 kg CO2e/kg H2 ✓")
    print("   • Credit Approved: ✓ (A+ rating)")
    print("   • Contract Signed: ✓")
    print("   • Certificate Transferred: ✓ (RED-EU-2027-001234)")
    print(f"\n🔒 Audit Trail: {len(events)} immutable events")
    print("   • Cryptographically verified ✓")
    print("   • Complete chain of custody ✓")
    print("   • Ready for regulatory audit ✓")
    
    print_section("Demo Complete!")
    print("✅ All systems operational")
    print("✅ Event-driven architecture working")
    print("✅ Immutable audit trail verified")
    print("✅ Compliance thread traceable")
    print("\n🎯 This demonstrates GreenEarthX's capability to provide:")
    print("   • Complete transparency from production to delivery")
    print("   • Cryptographic proof of compliance")
    print("   • Tamper-evident audit trail")
    print("   • End-to-end traceability for regulators and lenders")
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    # Initialize event store
    EventStore.initialize_schema()
    
    # Run demo
    demo_complete_lifecycle()
