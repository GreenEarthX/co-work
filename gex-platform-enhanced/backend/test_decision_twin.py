#!/usr/bin/env python3
"""
Decision Twin - Live Test Script
Demonstrates the power of the certification engine
"""
import requests
import json
from datetime import datetime


BASE_URL = "http://localhost:8000/api/v1/decision-twin"


def print_section(title):
    """Pretty print section headers"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def test_red_iii():
    """Test RED III evaluation"""
    print_section("TEST 1: RED III Evaluation (EU)")
    
    # Excellent project
    data = {
        "molecule": "H2",
        "ghg_intensity": 0.35,
        "renewable_electricity_pct": 100,
        "temporal_matching": "monthly",
        "geographical_correlation": True
    }
    
    print("Project Data:")
    print(json.dumps(data, indent=2))
    print("\nCalling Decision Twin...")
    
    response = requests.post(f"{BASE_URL}/evaluate/red-iii", json=data)
    
    if response.status_code == 200:
        result = response.json()["evaluation"]
        print(f"\n✅ Status: {result['status'].upper()}")
        print(f"📊 Summary: {result['summary']}")
        
        if result.get("subsidy_value"):
            print(f"💰 Subsidy Value: €{result['subsidy_value']['amount_eur_kg']}/kg")
        
        print("\n📋 Checks Performed:")
        for check in result["checks"]:
            status = "✅" if check["passed"] else "❌"
            print(f"  {status} {check['check']}: {check.get('actual', 'N/A')}")
        
        if result.get("warnings"):
            print("\n⚠️  Warnings:")
            for warning in result["warnings"]:
                print(f"  - {warning['message']}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)


def test_45v():
    """Test 45V evaluation"""
    print_section("TEST 2: 45V Evaluation (US Clean Hydrogen)")
    
    # Tier 4 project WITHOUT prevailing wage
    data = {
        "ghg_intensity": 0.40,
        "electricity_source": "wind",
        "electricity_age_months": 18,
        "prevailing_wage_compliance": False
    }
    
    print("Project Data:")
    print(json.dumps(data, indent=2))
    print("\nCalling Decision Twin...")
    
    response = requests.post(f"{BASE_URL}/evaluate/45v", json=data)
    
    if response.status_code == 200:
        result = response.json()["evaluation"]
        print(f"\n✅ Status: {result['status'].upper()}")
        print(f"🏆 Tier: {result.get('tier', 'N/A')}")
        print(f"📊 Summary: {result['summary']}")
        
        if result.get("credit_value"):
            cv = result["credit_value"]
            print(f"\n💰 Credit Value:")
            print(f"  Base Credit: ${cv['base_credit_usd_kg']}/kg")
            print(f"  Wage Multiplier: {cv['wage_multiplier']}x")
            print(f"  Final Credit: ${cv['final_credit_usd_kg']}/kg")
        
        print("\n📋 Checks Performed:")
        for check in result["checks"]:
            status = "✅" if check.get("passed") else "⚠️"
            print(f"  {status} {check['check']}")
        
        if result.get("warnings"):
            print("\n⚠️  Critical Warnings:")
            for warning in result["warnings"]:
                print(f"  - {warning['message']}")
                if warning.get("recommendation"):
                    print(f"    💡 {warning['recommendation']}")
    else:
        print(f"❌ Error: {response.status_code}")


def test_comprehensive():
    """Test comprehensive multi-scheme evaluation"""
    print_section("TEST 3: Comprehensive Multi-Scheme Evaluation")
    
    # German H2 project
    data = {
        "molecule": "H2",
        "country": "Germany",
        "ghg_intensity": 0.35,
        "renewable_electricity_pct": 100,
        "electricity_source": "renewable",
        "electricity_age_months": 12,
        "temporal_matching": "monthly",
        "geographical_correlation": True,
        "prevailing_wage": False,
        "project_id": "H2-Hamburg-Demo",
        "correlation_id": f"TEST-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    }
    
    print("Project Data:")
    print(f"  Molecule: {data['molecule']}")
    print(f"  Country: {data['country']}")
    print(f"  GHG Intensity: {data['ghg_intensity']} kg CO2e/kg")
    print(f"  Renewable Electricity: {data['renewable_electricity_pct']}%")
    
    print("\nCalling Decision Twin for comprehensive evaluation...")
    
    response = requests.post(f"{BASE_URL}/evaluate/comprehensive", json=data)
    
    if response.status_code == 200:
        result = response.json()["comprehensive_evaluation"]
        
        print(f"\n📊 Evaluation Summary:")
        print(f"  Schemes Evaluated: {', '.join(result['schemes_evaluated'])}")
        print(f"  Eligible Schemes: {', '.join(result['eligible_schemes']) if result['eligible_schemes'] else 'None'}")
        print(f"  Ineligible Schemes: {', '.join(result['ineligible_schemes']) if result['ineligible_schemes'] else 'None'}")
        
        if result.get("total_subsidy_value"):
            print(f"\n💰 Total Subsidy Value: €{result['total_subsidy_value']:.2f}/kg")
        
        # Show details for each scheme
        for scheme in result['schemes_evaluated']:
            if scheme in result:
                scheme_result = result[scheme]
                print(f"\n📋 {scheme} Details:")
                print(f"  Status: {scheme_result['status'].upper()}")
                
                if scheme_result.get("checks"):
                    passed = sum(1 for c in scheme_result["checks"] if c.get("passed"))
                    total = len(scheme_result["checks"])
                    print(f"  Checks: {passed}/{total} passed")
                
                if scheme_result.get("subsidy_value"):
                    print(f"  Value: €{scheme_result['subsidy_value']['amount_eur_kg']}/kg")
    else:
        print(f"❌ Error: {response.status_code}")


def test_knowledge_base():
    """Test knowledge base endpoints"""
    print_section("TEST 4: Knowledge Base - Supported Schemes")
    
    response = requests.get(f"{BASE_URL}/knowledge-base/schemes")
    
    if response.status_code == 200:
        schemes = response.json()["schemes"]
        print(f"📚 {len(schemes)} Certification Schemes Available:\n")
        
        for scheme in schemes:
            print(f"  {scheme['code']}: {scheme['name']}")
            print(f"    Jurisdiction: {scheme['jurisdiction']}")
            print(f"    Applies to: {', '.join(scheme['applies_to'])}")
            print()


def test_failing_project():
    """Test a project that FAILS certification"""
    print_section("TEST 5: Failing Project - See Recommendations")
    
    # Poor project - high GHG, low renewable
    data = {
        "molecule": "H2",
        "ghg_intensity": 3.5,  # Very high!
        "renewable_electricity_pct": 50,  # Too low!
        "temporal_matching": "annual",
        "geographical_correlation": False
    }
    
    print("Poorly Designed Project:")
    print(json.dumps(data, indent=2))
    print("\nCalling Decision Twin...")
    
    response = requests.post(f"{BASE_URL}/evaluate/red-iii", json=data)
    
    if response.status_code == 200:
        result = response.json()["evaluation"]
        print(f"\n❌ Status: {result['status'].upper()}")
        print(f"📊 Summary: {result['summary']}")
        
        if result.get("failures"):
            print(f"\n❌ Failures ({len(result['failures'])}):")
            for failure in result["failures"]:
                print(f"  - {failure['check']}: {failure['reason']}")
                if failure.get("gap"):
                    print(f"    Gap: {failure['gap']}")
        
        if result.get("recommendations"):
            print("\n💡 Recommendations to Qualify:")
            for rec in result["recommendations"]:
                print(f"  {rec['action']}:")
                for option in rec.get("options", []):
                    print(f"    • {option}")


if __name__ == "__main__":
    print("\n" + "🏆" * 40)
    print("  DECISION TWIN - Live Demonstration")
    print("  Your Competitive Moat in Action!")
    print("🏆" * 40)
    
    try:
        # Test basic connectivity
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print("\n❌ Error: Decision Twin API not available")
            print("   Make sure backend is running on port 8000")
            exit(1)
        
        print(f"\n✅ Decision Twin API: {response.json()}")
        
        # Run tests
        test_red_iii()
        test_45v()
        test_comprehensive()
        test_knowledge_base()
        test_failing_project()
        
        print("\n" + "=" * 80)
        print("  ✅ All tests complete!")
        print("  💎 Your Decision Twin is operational and powerful!")
        print("=" * 80 + "\n")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Cannot connect to backend")
        print("   Make sure backend is running: uvicorn app.main:app --reload --port 8000")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
