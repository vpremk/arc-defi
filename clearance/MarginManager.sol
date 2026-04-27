// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// CCP Function 3: Margin / Collateral Management
//
// CCPs collect initial margin at trade registration and issue intra-day variation
// margin calls when mark-to-market moves erode a member's buffer. NSCC processes
// these in overnight batch windows, creating a 24-hour exposure gap between a
// move occurring and collateral being collected.
//
// This contract replicates both functions on-chain:
//   - postInitialMargin: locks collateral before a trade is registered (Steps 7–8)
//   - postVariationMargin: top-up in response to an intra-day margin call
//   - issueMarginCall: admin triggers when MTM moves drop margin below maintenance
//   - declareBreach: liquidates margin if call is not met within the window
//
// On ARC: directly replaces NSCC margin management. No overnight batch window.
// Margin calls can be issued and met within minutes.
// DefaultWaterfall must be authorized to call declareBreach.

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

contract MarginManager {
    uint256 public constant MARGIN_CALL_WINDOW = 4 hours;

    struct MarginAccount {
        uint256 initialMargin;
        uint256 variationMargin;
        uint256 maintenanceThreshold; // admin-set per participant risk profile
        bool    marginCallPending;
        uint256 marginCallAmount;
        uint256 marginCallDeadline;
    }

    IERC20  public immutable usdc;
    address public admin;

    mapping(address => bool)          public registered;
    mapping(address => MarginAccount) public accounts;
    mapping(address => bool)          public authorized; // e.g. DefaultWaterfall

    event ParticipantRegistered(address indexed participant, uint256 maintenanceThreshold);
    event InitialMarginPosted(address indexed participant, uint256 amount, uint256 total);
    event VariationMarginPosted(address indexed participant, uint256 amount, uint256 total);
    event MarginCallIssued(address indexed participant, uint256 amount, uint256 deadline);
    event MarginCallMet(address indexed participant);
    event MarginCallBreached(address indexed participant, uint256 liquidated);
    event ExcessWithdrawn(address indexed participant, uint256 amount);

    modifier onlyAdmin() {
        require(msg.sender == admin, "admin only");
        _;
    }

    modifier onlyAdminOrAuthorized() {
        require(msg.sender == admin || authorized[msg.sender], "unauthorized");
        _;
    }

    constructor(address _usdc) {
        usdc  = IERC20(_usdc);
        admin = msg.sender;
    }

    function registerParticipant(address participant, uint256 maintenanceThreshold) external onlyAdmin {
        require(!registered[participant], "already registered");
        registered[participant] = true;
        accounts[participant].maintenanceThreshold = maintenanceThreshold;
        emit ParticipantRegistered(participant, maintenanceThreshold);
    }

    // Lock initial margin before a trade is registered in Novation.
    // Must be called and confirmed before the exchange accepts the order.
    function postInitialMargin(uint256 amount) external {
        require(registered[msg.sender], "not registered");
        usdc.transferFrom(msg.sender, address(this), amount);
        accounts[msg.sender].initialMargin += amount;
        emit InitialMarginPosted(msg.sender, amount, totalMargin(msg.sender));
    }

    // Post variation margin intra-day, either proactively or in response to a call.
    function postVariationMargin(uint256 amount) external {
        require(registered[msg.sender], "not registered");
        usdc.transferFrom(msg.sender, address(this), amount);
        accounts[msg.sender].variationMargin += amount;

        MarginAccount storage acct = accounts[msg.sender];
        if (acct.marginCallPending
            && totalMargin(msg.sender) >= acct.maintenanceThreshold + acct.marginCallAmount) {
            acct.marginCallPending = false;
            acct.marginCallAmount  = 0;
            emit MarginCallMet(msg.sender);
        }

        emit VariationMarginPosted(msg.sender, amount, totalMargin(msg.sender));
    }

    // Admin issues a margin call when MTM moves drop total margin below maintenance.
    // Participant has MARGIN_CALL_WINDOW (4 hours) to meet the call.
    function issueMarginCall(address participant, uint256 amount) external onlyAdmin {
        MarginAccount storage acct = accounts[participant];
        require(registered[participant], "not registered");
        require(!acct.marginCallPending, "call already pending");
        require(totalMargin(participant) < acct.maintenanceThreshold, "margin sufficient");

        acct.marginCallPending  = true;
        acct.marginCallAmount   = amount;
        acct.marginCallDeadline = block.timestamp + MARGIN_CALL_WINDOW;
        emit MarginCallIssued(participant, amount, acct.marginCallDeadline);
    }

    // Called by admin or DefaultWaterfall when the deadline passes unmet.
    // Liquidates the full margin balance; returns the amount for the waterfall.
    function declareBreach(address participant) external onlyAdminOrAuthorized returns (uint256 liquidated) {
        MarginAccount storage acct = accounts[participant];
        require(acct.marginCallPending, "no pending call");
        require(block.timestamp > acct.marginCallDeadline, "deadline not reached");

        liquidated = totalMargin(participant);
        acct.initialMargin    = 0;
        acct.variationMargin  = 0;
        acct.marginCallPending = false;

        // USDC stays in this contract; DefaultWaterfall draws it in the next stage.
        emit MarginCallBreached(participant, liquidated);
    }

    // Participant withdraws margin above the maintenance threshold when no call is pending.
    function withdrawExcess(uint256 amount) external {
        MarginAccount storage acct = accounts[msg.sender];
        require(!acct.marginCallPending, "call pending");

        uint256 total  = totalMargin(msg.sender);
        uint256 excess = total > acct.maintenanceThreshold ? total - acct.maintenanceThreshold : 0;
        require(amount <= excess, "exceeds excess margin");

        // Reduce from variation margin first (initial margin is the locked base).
        if (amount <= acct.variationMargin) {
            acct.variationMargin -= amount;
        } else {
            uint256 fromVariation = acct.variationMargin;
            acct.variationMargin  = 0;
            acct.initialMargin   -= (amount - fromVariation);
        }

        usdc.transfer(msg.sender, amount);
        emit ExcessWithdrawn(msg.sender, amount);
    }

    function totalMargin(address participant) public view returns (uint256) {
        MarginAccount storage acct = accounts[participant];
        return acct.initialMargin + acct.variationMargin;
    }

    function isMarginSufficient(address participant) external view returns (bool) {
        return totalMargin(participant) >= accounts[participant].maintenanceThreshold;
    }

    function authorize(address caller) external onlyAdmin {
        authorized[caller] = true;
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        admin = newAdmin;
    }
}
