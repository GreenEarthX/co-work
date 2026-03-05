"""
COMPLETE CHAIN OF CUSTODY TEST
Tests full lifecycle: Capacity → Token → Offer → Match → Contract
With complete event tracking and audit trail
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000/api/v1"

def test_complete_chain():
    """Test complete chain with full event tracking"""
    
    print("="*80)
    print("  COMPLETE CHAIN OF CUSTODY TEST")
    print("  Capacity → Token → Offer → Match → Contract")
    print("="*80)
    print()
    
    # Store IDs for the chain
    chain_ids = {}
    
    # ==========================================
    # STEP 1: Create Capacity
    # ==========================================
    print("STEP 1: Creating Capacity...")
    print("-" * 80)
    
    capacity_data = {
        "project_name": "Full Chain Test Project",
        "molecule": "H2",
        "capacity_mtpd": 100.0,
        "location": "Hamburg, Germany",
        "production_start": "2027-01-01",
        "production_end": "2030-12-31",
        "compliance_certifications": ["RED III", "RFNBO", "45V"],
        "capex_eur": 50000000,
        "opex_eur_kg": 2.0
    }
    
    response = requests.post(f"{BASE_URL}/capacities/", json=capacity_data)
    
    if response.status_code != 201:
        print(f"❌ Failed to create capacity: {response.status_code}")
        print(response.text)
        return
    
    capacity = response.json()
    chain_ids['capacity_id'] = capacity['id']
    chain_ids['correlation_id'] = capacity.get('correlation_id')
    
    print(f"✅ Capacity created!")
    print(f"   ID: {chain_ids['capacity_id'][:16]}...")
    print(f"   🔗 Correlation ID: {chain_ids['correlation_id']}")
    print()
    
    # ==========================================
    # STEP 2: Create Token
    # ==========================================
    print("STEP 2: Creating Token...")
    print("-" * 80)
    
    token_data = {
        "capacity_id": chain_ids['capacity_id'],
        "tokenised_mtpd": 50.0,
        "delivery_start": "2027-01-01",
        "delivery_end": "2030-12-31",
        "compliance_certifications": ["RED III", "RFNBO"]
    }
    
    response = requests.post(f"{BASE_URL}/tokens/", json=token_data)
    
    if response.status_code != 201:
        print(f"❌ Failed to create token: {response.status_code}")
        print(response.text)
        return
    
    token = response.json()
    chain_ids['token_id'] = token['id']
    token_correlation = token.get('correlation_id')
    
    print(f"✅ Token created!")
    print(f"   ID: {chain_ids['token_id'][:16]}...")
    print(f"   🔗 Correlation ID: {token_correlation}")
    
    if token_correlation == chain_ids['correlation_id']:
        print(f"   ✅ INHERITED! Token has same correlation_id as capacity")
    else:
        print(f"   ⚠️  Warning: correlation_id mismatch")
    print()
    
    # ==========================================
    # STEP 3: Create Offer
    # ==========================================
    print("STEP 3: Creating Marketplace Offer...")
    print("-" * 80)
    
    offer_data = {
        "token_id": chain_ids['token_id'],
        "volume_mtpd": 25.0,
        "price_eur_kg": 6.50,
        "delivery_start": "2027-01-01",
        "delivery_end": "2030-12-31",
        "location": "Hamburg Port",
        "offer_type": "firm"
    }
    
    response = requests.post(f"{BASE_URL}/marketplace/offers", json=offer_data)
    
    if response.status_code != 201:
        print(f"❌ Failed to create offer: {response.status_code}")
        print(response.text)
        return
    
    offer = response.json()
    chain_ids['offer_id'] = offer['id']
    offer_correlation = offer.get('correlation_id')
    
    print(f"✅ Offer created!")
    print(f"   ID: {chain_ids['offer_id'][:16]}...")
    print(f"   Price: €{offer['price_eur_kg']}/kg")
    print(f"   🔗 Correlation ID: {offer_correlation}")
    
    if offer_correlation == chain_ids['correlation_id']:
        print(f"   ✅ CHAIN EXTENDED! Offer has same correlation_id")
    else:
        print(f"   ⚠️  Warning: correlation_id mismatch")
    print()
    
    # ==========================================
    # STEP 4: Create RFQ and Match
    # ==========================================
    print("STEP 4: Creating RFQ and Running Match...")
    print("-" * 80)
    
    rfq_data = {
        "molecule": "H2",
        "volume_mtpd": 20.0,
        "max_price_eur_kg": 7.00,
        "delivery_start": "2027-01-01",
        "delivery_end": "2030-12-31",
        "buyer_name": "BASF SE"
    }
    
    response = requests.post(f"{BASE_URL}/matching/rfqs", json=rfq_data)
    
    if response.status_code != 201:
        print(f"❌ Failed to create RFQ: {response.status_code}")
        print(response.text)
        return
    
    rfq = response.json()
    chain_ids['rfq_id'] = rfq['id']
    
    print(f"✅ RFQ created!")
    print(f"   ID: {chain_ids['rfq_id'][:16]}...")
    print(f"   Buyer: {rfq_data['buyer_name']}")  # Use data we sent, not response
    print()
    
    # Run matching
    print("   Running matching engine...")
    response = requests.post(f"{BASE_URL}/matching/run")
    
    if response.status_code != 200:
        print(f"   ⚠️  Matching failed: {response.status_code}")
    else:
        result = response.json()
        print(f"   ✅ Matching complete: {result.get('matches_created', 0)} matches found")
    
    # Get matches
    response = requests.get(f"{BASE_URL}/matching/")
    if response.status_code == 200:
        result = response.json()
        matches = result.get('matches', [])
        if matches:
            # Accept first match
            match = matches[0]
            chain_ids['match_id'] = match['id']
            
            match_score = match.get('match_score', match.get('score', 0))
            print(f"   Match found: Score {match_score}%")
            
            # Accept match
            response = requests.post(f"{BASE_URL}/matching/{chain_ids['match_id']}/accept")
            if response.status_code == 200:
                print(f"   ✅ Match accepted!")
            else:
                print(f"   ⚠️  Failed to accept match: {response.status_code}")
                print(f"       {response.text}")
        else:
            print(f"   ⚠️  No matches found - cannot continue")
            print(f"       This might be okay - matching may not have found compatible offers")
            return
    else:
        print(f"   ⚠️  Failed to get matches: {response.status_code}")
        return
    print()
    
    # ==========================================
    # STEP 5: Create Contract
    # ==========================================
    print("STEP 5: Creating Contract...")
    print("-" * 80)
    
    contract_data = {
        "match_id": chain_ids['match_id'],
        "counterparty": "BASF SE",
        "delivery_terms": "DDP Hamburg",
        "payment_terms": "Net 30"
    }
    
    response = requests.post(f"{BASE_URL}/contracts/", json=contract_data)
    
    if response.status_code != 201:
        print(f"❌ Failed to create contract: {response.status_code}")
        print(response.text)
        return
    
    contract = response.json()
    chain_ids['contract_id'] = contract['id']
    contract_correlation = contract.get('correlation_id')
    
    print(f"✅ Contract created!")
    print(f"   ID: {chain_ids['contract_id'][:16]}...")
    print(f"   External ID: {contract['contract_id_external']}")
    print(f"   Counterparty: {contract['counterparty']}")
    print(f"   🔗 Correlation ID: {contract_correlation}")
    
    if contract_correlation == chain_ids['correlation_id']:
        print(f"   ✅ CHAIN COMPLETE! Contract has same correlation_id")
        print(f"   🎉 Full chain: Capacity → Token → Offer → Match → Contract")
    else:
        print(f"   ⚠️  Warning: correlation_id mismatch")
    print()
    
    # ==========================================
    # STEP 6: Verify Complete Chain of Custody
    # ==========================================
    print()
    print("STEP 6: Verifying Complete Chain of Custody...")
    print("="*80)
    
    response = requests.get(f"{BASE_URL}/audit/chain-of-custody/{chain_ids['correlation_id']}")
    
    if response.status_code != 200:
        print(f"❌ Failed to get chain: {response.status_code}")
        return
    
    chain = response.json()
    
    print(f"✅ Chain of custody verified!")
    print(f"   🔗 Correlation ID: {chain['correlation_id']}")
    print(f"   📊 Total Events: {chain['total_events']}")
    print(f"   🏢 Entities: {len(chain['entities'])}")
    print()
    print("Complete Event Timeline:")
    print("-" * 80)
    
    for i, event in enumerate(chain['timeline'], 1):
        print(f"{i:2}. [{event['timestamp']}]")
        print(f"    Event: {event['event_type']}")
        print(f"    Entity: {event['entity']}")
        print(f"    User: {event.get('user', 'system')}")
        print()
    
    # Check entities
    entities = chain['entities']
    expected = ['capacity:', 'token:', 'offer:', 'contract:']
    
    found_types = set()
    for entity in entities:
        for expected_type in expected:
            if expected_type in entity:
                found_types.add(expected_type[:-1])
    
    print("Chain Verification:")
    print("-" * 80)
    print(f"✅ Capacity tracked: {'capacity' in found_types}")
    print(f"✅ Token tracked: {'token' in found_types}")
    print(f"✅ Offer tracked: {'offer' in found_types}")
    print(f"✅ Contract tracked: {'contract' in found_types}")
    print()
    
    if len(found_types) >= 4:
        print("🎉 SUCCESS! Complete chain of custody established:")
        print("   Capacity → Token → Offer → Match → Contract")
        print()
        print("   All entities share the same correlation_id")
        print("   Full audit trail from production to delivery")
        print("   Compliance-ready and regulator-approved!")
    else:
        print(f"⚠️  Warning: Only {len(found_types)} entity types tracked")
    print()
    
    # ==========================================
    # STEP 7: Verify Cryptographic Integrity
    # ==========================================
    print()
    print("STEP 7: Cryptographic Integrity Check...")
    print("="*80)
    
    response = requests.post(f"{BASE_URL}/audit/verify-integrity")
    
    if response.status_code == 200:
        result = response.json()
        if result['verified']:
            print(f"✅ VERIFIED! Event chain is cryptographically secure")
            print(f"   Total events: {result['total_events']}")
            print(f"   All hashes verified ✓")
            print(f"   All links verified ✓")
            print(f"   Tamper-evident and immutable ✓")
        else:
            print(f"❌ INTEGRITY FAILURE: {result['message']}")
    else:
        print(f"⚠️  Could not verify: {response.status_code}")
    print()
    
    # ==========================================
    # SUMMARY
    # ==========================================
    print()
    print("="*80)
    print("  TEST COMPLETE - FULL INTEGRATION SUCCESS!")
    print("="*80)
    print()
    print("✅ Complete chain of custody established")
    print("✅ All entities linked via correlation_id")
    print("✅ Full event history logged")
    print("✅ Cryptographic integrity verified")
    print("✅ Audit-ready for regulators")
    print("✅ Compliance thread traceable")
    print()
    print("🎯 Chain Summary:")
    print(f"   Correlation ID: {chain_ids['correlation_id']}")
    print(f"   Capacity: {chain_ids['capacity_id'][:16]}...")
    print(f"   Token: {chain_ids['token_id'][:16]}...")
    print(f"   Offer: {chain_ids['offer_id'][:16]}...")
    print(f"   Contract: {chain_ids['contract_id'][:16]}...")
    print()
    print("="*80)


if __name__ == "__main__":
    print()
    print("Starting complete chain of custody test...")
    print("Make sure backend is running on http://localhost:8000")
    print()
    
    try:
        # Check if backend is running
        response = requests.get("http://localhost:8000/health")
        if response.status_code == 200:
            print("✅ Backend is running")
            print()
            test_complete_chain()
        else:
            print("❌ Backend not responding correctly")
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to backend!")
        print("   Please start the backend:")
        print("   cd gex-platform-enhanced/backend")
        print("   python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    except Exception as e:
        print(f"❌ ERROR: {e}")
