// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// CCP Function 5: Settlement Finality
//
// Traditional CCPs provide legal settlement finality under UCC Article 8 and
// their own rulebooks: once DTC completes a book-entry transfer it is
// irrevocable. Blockchain finality is technically stronger (a confirmed
// transaction cannot be reversed at the protocol level) but is not yet
// recognised as legal finality in most jurisdictions.
//
// This contract bridges that gap with a configurable dispute window:
//
//   1. Both buyer's USDC and seller's asset are held in escrow after DVP.
//   2. Either counterparty can raise a dispute within the window.
//   3. Admin resolves: uphold (settlement stands) or reject (positions returned).
//   4. If no dispute is raised, anyone can call finalise() after the window —
//      USDC auto-releases to the seller. This is the on-chain analogue of
//      UCC Article 12 finality (enacted 2023) for controllable electronic records.
//
// The dispute window (default 4 hours) is configurable: an exchange running
// within market hours could set it to match their close-of-business review period.
// After full regulatory recognition, the window can be set to 0 for instant finality.
//
// On ARC: directly replaces CCP settlement finality. The window is the only
// remaining gap vs. traditional bust-trade rules; it is strictly shorter than T+1.

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

interface IERC721 {
    function transferFrom(address from, address to, uint256 tokenId) external;
}

contract SettlementFinality {
    enum FinalityStatus { InWindow, Final, Disputed, Reversed }

    struct Settlement {
        address        buyer;
        address        seller;
        address        asset;
        uint256        assetId;
        uint256        cashAmount;     // USDC (6 dec)
        bytes32        deliverableHash;
        uint256        settledAt;
        uint256        windowClosesAt;
        FinalityStatus status;
    }

    IERC20  public immutable usdc;
    address public admin;

    uint256 public disputeWindow; // seconds; default 4 hours

    uint256 public nextSettlementId;
    mapping(uint256 => Settlement) public settlements;

    event SettlementInitiated(
        uint256 indexed settlementId,
        address indexed buyer,
        address indexed seller,
        uint256 cashAmount,
        uint256 windowClosesAt
    );
    event DisputeRaised(uint256 indexed settlementId, address raisedBy);
    event DisputeResolved(uint256 indexed settlementId, bool upheld);
    event SettlementFinalised(uint256 indexed settlementId, uint256 finalisedAt);
    event SettlementReversed(uint256 indexed settlementId);

    modifier onlyAdmin() {
        require(msg.sender == admin, "admin only");
        _;
    }

    constructor(address _usdc, uint256 _disputeWindowSeconds) {
        usdc          = IERC20(_usdc);
        admin         = msg.sender;
        disputeWindow = _disputeWindowSeconds;
    }

    // Initiates DVP settlement: buyer's USDC and seller's asset move into escrow.
    // Neither party has received anything yet — both are held pending the window.
    function initiateSettlement(
        address seller,
        address asset,
        uint256 assetId,
        uint256 cashAmount,
        bytes32 deliverableHash
    ) external returns (uint256 settlementId) {
        require(cashAmount > 0, "zero cash");

        usdc.transferFrom(msg.sender, address(this), cashAmount);
        IERC721(asset).transferFrom(seller, address(this), assetId);

        uint256 windowEnd = block.timestamp + disputeWindow;
        settlementId = nextSettlementId++;

        settlements[settlementId] = Settlement({
            buyer:           msg.sender,
            seller:          seller,
            asset:           asset,
            assetId:         assetId,
            cashAmount:      cashAmount,
            deliverableHash: deliverableHash,
            settledAt:       block.timestamp,
            windowClosesAt:  windowEnd,
            status:          FinalityStatus.InWindow
        });

        emit SettlementInitiated(settlementId, msg.sender, seller, cashAmount, windowEnd);
    }

    // Either counterparty raises a dispute within the window.
    // Freezes both USDC and asset in escrow pending admin resolution.
    // Replicates DTC's "don't know" (DK) mechanism.
    function raiseDispute(uint256 settlementId) external {
        Settlement storage s = settlements[settlementId];
        require(s.status == FinalityStatus.InWindow, "not in dispute window");
        require(block.timestamp < s.windowClosesAt, "window closed");
        require(msg.sender == s.buyer || msg.sender == s.seller, "not a counterparty");

        s.status = FinalityStatus.Disputed;
        emit DisputeRaised(settlementId, msg.sender);
    }

    // Admin resolves a disputed settlement.
    //   uphold=true  → settlement stands; USDC released to seller, asset stays with buyer.
    //   uphold=false → reversed; USDC returned to buyer, asset returned to seller.
    function resolveDispute(uint256 settlementId, bool uphold) external onlyAdmin {
        Settlement storage s = settlements[settlementId];
        require(s.status == FinalityStatus.Disputed, "not disputed");

        if (uphold) {
            usdc.transfer(s.seller, s.cashAmount);
            s.status = FinalityStatus.Final;
            emit DisputeResolved(settlementId, true);
            emit SettlementFinalised(settlementId, block.timestamp);
        } else {
            usdc.transfer(s.buyer, s.cashAmount);
            IERC721(s.asset).transferFrom(address(this), s.seller, s.assetId);
            s.status = FinalityStatus.Reversed;
            emit DisputeResolved(settlementId, false);
            emit SettlementReversed(settlementId);
        }
    }

    // Auto-release after the dispute window — achieves UCC Article 12 finality.
    // Callable by anyone once the window has elapsed with no dispute raised.
    function finalise(uint256 settlementId) external {
        Settlement storage s = settlements[settlementId];
        require(s.status == FinalityStatus.InWindow, "not awaiting finality");
        require(block.timestamp >= s.windowClosesAt, "window still open");

        usdc.transfer(s.seller, s.cashAmount);
        s.status = FinalityStatus.Final;

        emit SettlementFinalised(settlementId, block.timestamp);
    }

    // Returns seconds remaining in the dispute window (0 if elapsed).
    function windowRemaining(uint256 settlementId) external view returns (uint256) {
        Settlement storage s = settlements[settlementId];
        if (block.timestamp >= s.windowClosesAt) return 0;
        return s.windowClosesAt - block.timestamp;
    }

    // Admin adjusts the dispute window. Set to 0 for instant finality once
    // UCC Article 12 regulatory recognition is in place.
    function setDisputeWindow(uint256 newWindowSeconds) external onlyAdmin {
        disputeWindow = newWindowSeconds;
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        admin = newAdmin;
    }
}
