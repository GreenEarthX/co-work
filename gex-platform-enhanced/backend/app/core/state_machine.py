"""
GreenEarthX State Machine Engine
Enforce business rules and valid state transitions with event emission
"""
from typing import Dict, List, Callable, Optional, Any
from enum import Enum
from app.core.event_store import EventStore


class TransitionError(Exception):
    """Raised when invalid state transition attempted"""
    pass


class PreconditionError(Exception):
    """Raised when precondition not met"""
    pass


class StateMachine:
    """
    Generic state machine with event emission
    """
    
    def __init__(
        self,
        name: str,
        initial_state: str,
        transitions: Dict[str, List[str]],
        preconditions: Optional[Dict[str, Callable]] = None,
        postconditions: Optional[Dict[str, Callable]] = None
    ):
        """
        Initialize state machine
        
        Args:
            name: State machine name (e.g., 'capacity')
            initial_state: Initial state
            transitions: Dict of valid transitions {from_state: [to_states]}
            preconditions: Dict of precondition checks {transition: check_function}
            postconditions: Dict of postcondition actions {transition: action_function}
        """
        self.name = name
        self.initial_state = initial_state
        self.transitions = transitions
        self.preconditions = preconditions or {}
        self.postconditions = postconditions or {}
    
    def can_transition(self, from_state: str, to_state: str) -> bool:
        """Check if transition is valid"""
        return to_state in self.transitions.get(from_state, [])
    
    def validate_transition(
        self,
        aggregate_id: str,
        from_state: str,
        to_state: str,
        data: Optional[Dict] = None,
        user_id: Optional[str] = None
    ):
        """
        Validate transition and check preconditions
        
        Raises:
            TransitionError: If transition not valid
            PreconditionError: If precondition fails
        """
        # Check if transition is allowed
        if not self.can_transition(from_state, to_state):
            raise TransitionError(
                f"Invalid transition: {from_state} → {to_state}. "
                f"Valid transitions from {from_state}: {self.transitions.get(from_state, [])}"
            )
        
        # Check preconditions
        transition_key = f"{from_state}_to_{to_state}"
        if transition_key in self.preconditions:
            precondition_check = self.preconditions[transition_key]
            result = precondition_check(aggregate_id, data)
            
            if not result['valid']:
                raise PreconditionError(
                    f"Precondition failed for {from_state} → {to_state}: {result['reason']}"
                )
    
    def transition(
        self,
        aggregate_id: str,
        from_state: str,
        to_state: str,
        data: Optional[Dict] = None,
        user_id: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> str:
        """
        Execute state transition with event emission
        
        Returns:
            event_id: ID of the status_changed event
        """
        data = data or {}
        
        # Validate transition
        self.validate_transition(aggregate_id, from_state, to_state, data, user_id)
        
        # Emit status_changed event
        event_id = EventStore.append_event(
            event_type=f"{self.name}.status_changed",
            aggregate_type=self.name,
            aggregate_id=aggregate_id,
            data={
                "old_status": from_state,
                "new_status": to_state,
                **data
            },
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        # Execute postconditions (side effects)
        transition_key = f"{from_state}_to_{to_state}"
        if transition_key in self.postconditions:
            postcondition_action = self.postconditions[transition_key]
            postcondition_action(aggregate_id, data, event_id)
        
        return event_id
    
    def get_valid_transitions(self, current_state: str) -> List[str]:
        """Get list of valid next states"""
        return self.transitions.get(current_state, [])


# ============================================
# CAPACITY STATE MACHINE
# ============================================

CAPACITY_TRANSITIONS = {
    "draft": ["pending_verification", "cancelled"],
    "pending_verification": ["verified", "rejected"],
    "verified": ["tokenizing"],
    "tokenizing": ["tokenized"],
    "tokenized": ["allocated", "available"],
    "available": ["allocated"],
    "allocated": ["delivering"],
    "delivering": ["delivered"],
    "delivered": ["completed"],
    "completed": [],
    "rejected": ["draft"],  # Can resubmit
    "cancelled": []
}

def capacity_verification_precondition(capacity_id: str, data: Dict) -> Dict:
    """Check if capacity has required certifications for verification"""
    # In production, check actual certifications in database
    # For now, simple check
    return {
        "valid": True,
        "reason": None
    }

def capacity_tokenization_precondition(capacity_id: str, data: Dict) -> Dict:
    """Check if capacity is verified before tokenizing"""
    # Would check: capacity.status == 'verified'
    return {
        "valid": True,
        "reason": None
    }

CAPACITY_PRECONDITIONS = {
    "draft_to_pending_verification": capacity_verification_precondition,
    "verified_to_tokenizing": capacity_tokenization_precondition,
}

CAPACITY_STATE_MACHINE = StateMachine(
    name="capacity",
    initial_state="draft",
    transitions=CAPACITY_TRANSITIONS,
    preconditions=CAPACITY_PRECONDITIONS
)


# ============================================
# TOKEN STATE MACHINE
# ============================================

TOKEN_TRANSITIONS = {
    "minted": ["listed", "cancelled"],
    "listed": ["matched", "unlisted"],
    "matched": ["contracted"],
    "contracted": ["delivering"],
    "delivering": ["delivered"],
    "delivered": ["settled"],
    "settled": [],
    "unlisted": ["listed"],
    "cancelled": []
}

def token_listing_precondition(token_id: str, data: Dict) -> Dict:
    """Check if token can be listed"""
    # Would check: token has valid compliance certs
    return {
        "valid": True,
        "reason": None
    }

TOKEN_PRECONDITIONS = {
    "minted_to_listed": token_listing_precondition,
}

TOKEN_STATE_MACHINE = StateMachine(
    name="token",
    initial_state="minted",
    transitions=TOKEN_TRANSITIONS,
    preconditions=TOKEN_PRECONDITIONS
)


# ============================================
# CONTRACT STATE MACHINE
# ============================================

CONTRACT_TRANSITIONS = {
    "draft": ["pending_credit_check", "cancelled"],
    "pending_credit_check": ["credit_approved", "credit_rejected"],
    "credit_approved": ["pending_signature"],
    "pending_signature": ["partially_signed"],
    "partially_signed": ["fully_signed"],
    "fully_signed": ["delivering"],
    "delivering": ["delivered"],
    "delivered": ["payment_pending"],
    "payment_pending": ["fulfilled"],
    "fulfilled": [],
    "credit_rejected": ["draft"],  # Can resubmit
    "cancelled": []
}

def contract_credit_check_precondition(contract_id: str, data: Dict) -> Dict:
    """Check if contract has required data for credit check"""
    # Would check: counterparty creditworthiness, volume, etc.
    return {
        "valid": True,
        "reason": None
    }

def contract_signature_precondition(contract_id: str, data: Dict) -> Dict:
    """Check if contract can be signed"""
    # Would check: credit approved, terms finalized
    return {
        "valid": True,
        "reason": None
    }

CONTRACT_PRECONDITIONS = {
    "draft_to_pending_credit_check": contract_credit_check_precondition,
    "credit_approved_to_pending_signature": contract_signature_precondition,
}

CONTRACT_STATE_MACHINE = StateMachine(
    name="contract",
    initial_state="draft",
    transitions=CONTRACT_TRANSITIONS,
    preconditions=CONTRACT_PRECONDITIONS
)


# ============================================
# OFFER STATE MACHINE
# ============================================

OFFER_TRANSITIONS = {
    "draft": ["active", "cancelled"],
    "active": ["matched", "expired", "withdrawn"],
    "matched": ["contracted"],
    "contracted": ["fulfilled"],
    "fulfilled": [],
    "expired": [],
    "withdrawn": [],
    "cancelled": []
}

OFFER_STATE_MACHINE = StateMachine(
    name="offer",
    initial_state="draft",
    transitions=OFFER_TRANSITIONS
)


# ============================================
# MATCH STATE MACHINE
# ============================================

MATCH_TRANSITIONS = {
    "pending": ["accepted", "rejected"],
    "accepted": ["contracted"],
    "contracted": ["fulfilled"],
    "fulfilled": [],
    "rejected": []
}
#============================================
# added 5 feb 2026 for DUE DILIGENCE PIPELINE
#============================================
# Find MATCH_STATE_MACHINE definition and add:

def match_accepted_postcondition(match_id: str, data: Dict, event_id: str):
    """
    When match is accepted, auto-create DD pipeline
    """
    import uuid
    
    # Create DD pipeline record
    dd_id = str(uuid.uuid4())
    
    # Emit DD pipeline created event
    EventStore.append_event(
        event_type="dd.pipeline_created",
        aggregate_type="dd_pipeline",
        aggregate_id=dd_id,
        data={
            "match_id": match_id,
            "status": "pending",
        },
        causation_id=event_id,
        correlation_id=data.get("correlation_id")
    )
    
    # Transition DD to KYC
    DD_STATE_MACHINE.transition(
        aggregate_id=dd_id,
        from_state="pending",
        to_state="kyc_in_progress",
        data={"match_id": match_id},
        causation_id=event_id,
        correlation_id=data.get("correlation_id")
    )

MATCH_POSTCONDITIONS = {
    "pending_to_accepted": match_accepted_postcondition,
}

MATCH_STATE_MACHINE = StateMachine(
    name="match",
    initial_state="pending",
    transitions=MATCH_TRANSITIONS,
    postconditions=MATCH_POSTCONDITIONS  # ADD THIS
)
#============================================
# END of DUE DILIGENCE PIPELINE additions
#============================================

MATCH_STATE_MACHINE = StateMachine(
    name="match",
    initial_state="pending",
    transitions=MATCH_TRANSITIONS
)


# ============================================
# STATE MACHINE REGISTRY
# ============================================

STATE_MACHINES = {
    "capacity": CAPACITY_STATE_MACHINE,
    "token": TOKEN_STATE_MACHINE,
    "contract": CONTRACT_STATE_MACHINE,
    "offer": OFFER_STATE_MACHINE,
    "match": MATCH_STATE_MACHINE,
}


def get_state_machine(aggregate_type: str) -> StateMachine:
    """Get state machine for entity type"""
    if aggregate_type not in STATE_MACHINES:
        raise ValueError(f"No state machine defined for {aggregate_type}")
    return STATE_MACHINES[aggregate_type]


def transition_state(
    aggregate_type: str,
    aggregate_id: str,
    from_state: str,
    to_state: str,
    data: Optional[Dict] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None
) -> str:
    """
    Convenience function to transition entity state
    
    Returns:
        event_id: ID of the status_changed event
    """
    sm = get_state_machine(aggregate_type)
    return sm.transition(
        aggregate_id=aggregate_id,
        from_state=from_state,
        to_state=to_state,
        data=data,
        user_id=user_id,
        correlation_id=correlation_id
    )


def get_valid_next_states(aggregate_type: str, current_state: str) -> List[str]:
    """Get valid next states for an entity"""
    sm = get_state_machine(aggregate_type)
    return sm.get_valid_transitions(current_state)


def can_transition_to(aggregate_type: str, from_state: str, to_state: str) -> bool:
    """Check if transition is valid"""
    sm = get_state_machine(aggregate_type)
    return sm.can_transition(from_state, to_state)

# ============================================
# added for DUE DILIGENCE PIPELINE 5 feb 2026
#  DUE DILIGENCE STATE MACHINE (NEW)
# ============================================

DD_TRANSITIONS = {
    "pending": ["kyc_in_progress"],
    "kyc_in_progress": ["kyc_approved", "kyc_rejected"],
    "kyc_approved": ["credit_check_in_progress"],
    "credit_check_in_progress": ["credit_approved", "credit_rejected"],
    "credit_approved": ["financial_model_running"],
    "financial_model_running": ["financial_model_complete"],
    "financial_model_complete": ["technical_dd_in_progress", "loop_back_to_matching"],  # NEW: loop back
    "technical_dd_in_progress": ["technical_approved", "technical_rejected"],
    "technical_approved": ["legal_dd_in_progress"],
    "legal_dd_in_progress": ["legal_approved", "legal_rejected"],
    "legal_approved": ["complete"],
    "complete": [],
    "loop_back_to_matching": [],  # Terminal state for renegotiation
    "kyc_rejected": ["pending"],  # Can restart
    "credit_rejected": ["pending"],
    "technical_rejected": ["pending"],
    "legal_rejected": ["pending"],
}

def dd_financial_model_precondition(dd_id: str, data: Dict) -> Dict:
    """Check if credit is approved before running financial model"""
    # In production: check that credit_check is approved
    return {
        "valid": True,
        "reason": None
    }

def dd_financial_model_postcondition(dd_id: str, data: Dict, event_id: str):
    """
    AUTO-TRIGGER financial model when entering financial_model_running state
    """
    from app.services.financial_model import run_financial_model_for_match
    
    # Extract match_id from dd_id (assuming dd_id contains match_id)
    match_id = data.get("match_id")
    
    if match_id:
        # Run financial model asynchronously
        result = run_financial_model_for_match(match_id)
        
        # Store result in event store
        EventStore.append_event(
            event_type="dd.financial_model_completed",
            aggregate_type="dd_pipeline",
            aggregate_id=dd_id,
            data={
                "match_id": match_id,
                "bankability": result["bankability"],
                "dscr_base": result["base"]["dscr"],
                "dscr_stress": result["stress"]["dscr"],
                "irr_base": result["base"]["equity_irr_proxy"],
                "irr_stress": result["stress"]["equity_irr_proxy"],
            },
            causation_id=event_id,
            correlation_id=data.get("correlation_id")
        )
        
        # Auto-transition to complete state
        if result["bankability"] == "GREEN":
            DD_STATE_MACHINE.transition(
                aggregate_id=dd_id,
                from_state="financial_model_running",
                to_state="financial_model_complete",
                data={"bankability": "GREEN"},
                correlation_id=data.get("correlation_id")
            )
        elif result["bankability"] == "AMBER":
            # Stay in financial_model_complete for manual review
            DD_STATE_MACHINE.transition(
                aggregate_id=dd_id,
                from_state="financial_model_running",
                to_state="financial_model_complete",
                data={"bankability": "AMBER", "requires_review": True},
                correlation_id=data.get("correlation_id")
            )
        else:  # RED
            # Default to loop back option
            DD_STATE_MACHINE.transition(
                aggregate_id=dd_id,
                from_state="financial_model_running",
                to_state="loop_back_to_matching",
                data={"bankability": "RED", "reason": "DSCR below threshold"},
                correlation_id=data.get("correlation_id")
            )

DD_PRECONDITIONS = {
    "credit_approved_to_financial_model_running": dd_financial_model_precondition,
}

DD_POSTCONDITIONS = {
    "credit_approved_to_financial_model_running": dd_financial_model_postcondition,
}

DD_STATE_MACHINE = StateMachine(
    name="dd_pipeline",
    initial_state="pending",
    transitions=DD_TRANSITIONS,
    preconditions=DD_PRECONDITIONS,
    postconditions=DD_POSTCONDITIONS
)

# Add to registry
STATE_MACHINES["dd_pipeline"] = DD_STATE_MACHINE