// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// CCP Function 2: Multilateral Netting
//
// NSCC reduces gross settlement obligations by ~95% daily by offsetting
// buy and sell positions across all participants before settlement runs.
// Without this, every bilateral trade settles gross: 10 trades of 1M TSLA
// requires 10 full $250M settlements instead of one net position.
//
// This contract aggregates all trades registered in a netting cycle, computes
// each participant's net cash position (positive = receive USDC, negative = pay
// USDC), and settles only the net amount per participant. The gross-to-net
// reduction ratio is emitted on-chain for audit.
//
// On ARC: requires this contract as an additional build (Phase 4 of the
// adoption strategy). Not replaced automatically — must be deployed and wired
// into the exchange's order management system.

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

contract MultilateralNetting {
    struct NetPosition {
        int256  cashNet;   // USDC (6 dec); positive = receive, negative = pay
        bool    settled;
        uint256 settledAt;
    }

    IERC20  public immutable usdc;
    address public admin;

    uint256 public currentCycle;

    // cycleId => participant => net position
    mapping(uint256 => mapping(address => NetPosition)) public netPositions;

    // cycleId => participants list (for iteration at settlement)
    mapping(uint256 => address[]) internal cycleParticipants;
    mapping(uint256 => mapping(address => bool)) internal inCycle;

    // gross vs net tracking per cycle
    mapping(uint256 => uint256) public grossObligations; // sum of all buy-side cash
    mapping(uint256 => uint256) public netObligations;   // sum of absolute net positions
    mapping(uint256 => bool)    public cycleClosed;

    event TradeRegistered(
        uint256 indexed cycleId,
        address indexed buyer,
        address indexed seller,
        uint256 cashAmount
    );
    event NettingCycleExecuted(
        uint256 indexed cycleId,
        uint256 grossAmount,
        uint256 netAmount,
        uint256 reductionPct  // integer percentage; 9500 = 95.00%
    );
    event NetSettled(uint256 indexed cycleId, address indexed participant, int256 netAmount);

    modifier onlyAdmin() {
        require(msg.sender == admin, "admin only");
        _;
    }

    constructor(address _usdc) {
        usdc  = IERC20(_usdc);
        admin = msg.sender;
    }

    // Exchange calls this for every matched order pair within the current cycle.
    function registerTrade(
        address buyer,
        address seller,
        uint256 cashAmount
    ) external onlyAdmin {
        require(!cycleClosed[currentCycle], "cycle closed");
        require(cashAmount > 0, "zero amount");

        _trackParticipant(currentCycle, buyer);
        _trackParticipant(currentCycle, seller);

        netPositions[currentCycle][buyer].cashNet  -= int256(cashAmount);
        netPositions[currentCycle][seller].cashNet += int256(cashAmount);
        grossObligations[currentCycle]             += cashAmount;

        emit TradeRegistered(currentCycle, buyer, seller, cashAmount);
    }

    // Close the current netting cycle. Computes net obligations and advances the
    // cycle counter so a new cycle can begin. Emits the gross-to-net reduction.
    function executeNettingCycle() external onlyAdmin returns (uint256 closedCycle) {
        closedCycle = currentCycle;
        require(!cycleClosed[closedCycle], "already closed");

        // Net obligations = sum of absolute positive net positions
        // (equivalently, sum of absolute negative ones — they must balance)
        uint256 netSum;
        address[] storage participants = cycleParticipants[closedCycle];
        for (uint256 i = 0; i < participants.length; i++) {
            int256 net = netPositions[closedCycle][participants[i]].cashNet;
            if (net > 0) netSum += uint256(net);
        }
        netObligations[closedCycle] = netSum;
        cycleClosed[closedCycle]    = true;

        uint256 gross = grossObligations[closedCycle];
        uint256 reductionPct = gross > 0
            ? ((gross - netSum) * 10000) / gross
            : 0;

        emit NettingCycleExecuted(closedCycle, gross, netSum, reductionPct);
        currentCycle++;
    }

    // Settle a participant's net position for a closed cycle.
    // Net receivers: contract pays them. Net payers: they pay the contract.
    // Can be called by the participant themselves or by admin on their behalf.
    function settleNetPosition(uint256 cycleId, address participant) external {
        require(cycleClosed[cycleId], "cycle not closed");
        NetPosition storage pos = netPositions[cycleId][participant];
        require(!pos.settled, "already settled");

        pos.settled   = true;
        pos.settledAt = block.timestamp;

        if (pos.cashNet > 0) {
            usdc.transfer(participant, uint256(pos.cashNet));
        } else if (pos.cashNet < 0) {
            usdc.transferFrom(participant, address(this), uint256(-pos.cashNet));
        }
        // cashNet == 0: flat position, nothing moves

        emit NetSettled(cycleId, participant, pos.cashNet);
    }

    function getParticipants(uint256 cycleId) external view returns (address[] memory) {
        return cycleParticipants[cycleId];
    }

    function getNetPosition(uint256 cycleId, address participant) external view returns (int256) {
        return netPositions[cycleId][participant].cashNet;
    }

    function _trackParticipant(uint256 cycleId, address participant) internal {
        if (!inCycle[cycleId][participant]) {
            inCycle[cycleId][participant] = true;
            cycleParticipants[cycleId].push(participant);
        }
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        admin = newAdmin;
    }
}
