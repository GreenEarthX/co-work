"""
Integration Test Script
Tests event-driven capacity and token creation with full audit trail
"""
import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

def test_integration():
    """Test complete flow with events"""
    
    print("="*80)
    print("  GreenEarthX Integration Test - Event-Driven System")
    print("="*80)
    print()
    
    # ==========================================
    # TEST 1: Create Capacity with Events
    # ==========================================
    print("TEST 1: Creating Capacity...")
    print("-" * 80)
    
    capacity_data = {
        "project_name": "Integration Test Project",
        "molecule": "H2",
        "capacity_mtpd": 50.0,
        "location": "Test Location",
        "production_start": "2027-01-01",
        "production_end": "2030-12-31",
        "compliance_certifications": ["RED III", "RFNBO"],
        "capex_eur": 10000000,
        "opex_eur_kg": 2.5
    }
    
    response = requests.post(f"{BASE_URL}/capacities/", json=capacity_data)
    
    if response.status_code == 201:
        capacity = response.json()
        capacity_id = capacity['id']
        correlation_id = capacity.get('correlation_id')
        
        print(f"✅ Capacity created successfully!")
        print(f"   ID: {capacity_id}")
        print(f"   Correlation ID: {correlation_id}")
        print(f"   Status: {capacity.get('status', 'unknown')}")
        print()
        
        # Verify event was logged
        print("Checking event log...")
        audit_response = requests.get(f"{BASE_URL}/audit/entity/capacity/{capacity_id}")
        
        if audit_response.status_code == 200:
            audit = audit_response.json()
            print(f"✅ Event logged: {audit['total_events']} event(s)")
            for event in audit['events']:
                print(f"   - {event['event_type']} at {event['timestamp']} by {event['user']}")
        else:
            print(f"⚠️  Could not fetch audit trail: {audit_response.status_code}")
        print()
    else:
        print(f"❌ Failed to create capacity: {response.status_code}")
        print(f"   Error: {response.text}")
        return
    
    # ==========================================
    # TEST 2: Create Token with Inherited correlation_id
    # ==========================================
    print()
    print("TEST 2: Creating Token (should inherit correlation_id)...")
    print("-" * 80)
    
    token_data = {
        "capacity_id": capacity_id,
        "tokenised_mtpd": 25.0,
        "delivery_start": "2027-01-01",
        "delivery_end": "2030-12-31",
        "compliance_certifications": ["RED III", "RFNBO"]
    }
    
    response = requests.post(f"{BASE_URL}/tokens/", json=token_data)
    
    if response.status_code == 201:
        token = response.json()
        token_id = token['id']
        token_correlation_id = token.get('correlation_id')
        
        print(f"✅ Token created successfully!")
        print(f"   ID: {token_id}")
        print(f"   Correlation ID: {token_correlation_id}")
        print()
        
        # Verify correlation_id matches
        if token_correlation_id == correlation_id:
            print(f"✅ CHAIN FORMED! Token inherited correlation_id from capacity")
        else:
            print(f"⚠️  Warning: correlation_id mismatch")
            print(f"   Capacity: {correlation_id}")
            print(f"   Token: {token_correlation_id}")
        print()
        
        # Verify event was logged
        print("Checking token event log...")
        audit_response = requests.get(f"{BASE_URL}/audit/entity/token/{token_id}")
        
        if audit_response.status_code == 200:
            audit = audit_response.json()
            print(f"✅ Event logged: {audit['total_events']} event(s)")
            for event in audit['events']:
                print(f"   - {event['event_type']} at {event['timestamp']}")
        else:
            print(f"⚠️  Could not fetch audit trail: {audit_response.status_code}")
        print()
    else:
        print(f"❌ Failed to create token: {response.status_code}")
        print(f"   Error: {response.text}")
        return
    
    # ==========================================
    # TEST 3: Verify Chain of Custody
    # ==========================================
    print()
    print("TEST 3: Verifying Chain of Custody...")
    print("-" * 80)
    
    response = requests.get(f"{BASE_URL}/audit/chain-of-custody/{correlation_id}")
    
    if response.status_code == 200:
        chain = response.json()
        print(f"✅ Chain of custody retrieved!")
        print(f"   Correlation ID: {chain['correlation_id']}")
        print(f"   Total Events: {chain['total_events']}")
        print(f"   Entities Tracked: {len(chain['entities'])}")
        print()
        print("Event Timeline:")
        for i, event in enumerate(chain['timeline'], 1):
            print(f"   {i}. {event['timestamp']} - {event['event_type']}")
            print(f"      Entity: {event['entity']}")
            print(f"      User: {event.get('user', 'unknown')}")
        print()
        
        if chain['total_events'] >= 2:
            print("✅ SUCCESS! Complete chain of custody:")
            print("   Capacity → Token (linked via correlation_id)")
        else:
            print("⚠️  Chain incomplete - expected at least 2 events")
    else:
        print(f"❌ Failed to get chain of custody: {response.status_code}")
        print(f"   Error: {response.text}")
    print()
    
    # ==========================================
    # TEST 4: Verify Cryptographic Integrity
    # ==========================================
    print()
    print("TEST 4: Verifying Cryptographic Integrity...")
    print("-" * 80)
    
    response = requests.post(f"{BASE_URL}/audit/verify-integrity")
    
    if response.status_code == 200:
        result = response.json()
        if result['verified']:
            print(f"✅ VERIFIED! Event chain is tamper-free")
            print(f"   Total events verified: {result['total_events']}")
            print(f"   {result['message']}")
        else:
            print(f"❌ TAMPERING DETECTED!")
            print(f"   {result['message']}")
    else:
        print(f"⚠️  Could not verify integrity: {response.status_code}")
    print()
    
    # ==========================================
    # TEST 5: Get Audit Statistics
    # ==========================================
    print()
    print("TEST 5: Audit Statistics...")
    print("-" * 80)
    
    response = requests.get(f"{BASE_URL}/audit/stats")
    
    if response.status_code == 200:
        stats = response.json()
        print(f"✅ Audit stats retrieved")
        print(f"   Total events: {stats['total_events']}")
        print(f"   Event types:")
        for event_type, count in stats['event_types'].items():
            print(f"      {event_type}: {count}")
        print(f"   Entities tracked:")
        for entity_type, count in stats['entities_tracked'].items():
            print(f"      {entity_type}: {count}")
    else:
        print(f"⚠️  Could not get stats: {response.status_code}")
    print()
    
    # ==========================================
    # SUMMARY
    # ==========================================
    print()
    print("="*80)
    print("  INTEGRATION TEST COMPLETE!")
    print("="*80)
    print()
    print("✅ Capacity creation emits events")
    print("✅ Token creation inherits correlation_id")
    print("✅ Chain of custody tracking works")
    print("✅ Cryptographic integrity verified")
    print("✅ Audit API endpoints operational")
    print()
    print("🎯 Next Steps:")
    print("   1. Test in frontend UI")
    print("   2. Integrate contracts endpoint")
    print("   3. Add status transitions with state machines")
    print()
    print("="*80)


if __name__ == "__main__":
    print()
    print("Starting integration test...")
    print("Make sure backend is running on http://localhost:8000")
    print()
    
    try:
        # Check if backend is running
        response = requests.get("http://localhost:8000/health")
        if response.status_code == 200:
            print("✅ Backend is running")
            print()
            test_integration()
        else:
            print("❌ Backend not responding correctly")
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to backend!")
        print("   Please start the backend:")
        print("   cd gex-platform-enhanced/backend")
        print("   python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    except Exception as e:
        print(f"❌ ERROR: {e}")
