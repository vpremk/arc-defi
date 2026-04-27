// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// CCP Function 6: Default Management (Loss Absorption Waterfall)
//
// When a clearing member is declared insolvent, NSCC absorbs the loss through a
// strict waterfall. Each stage is exhausted before the next is drawn upon:
//
//   Stage 1 — Defaulted member's own margin (MarginManager.declareBreach)
//   Stage 2 — Shared guaranty pool (GuarantyPool.deployFunds)
//   Stage 3 — Pro-rata assessment on surviving members (GuarantyPool.issueAssessment)
//
// This contract orchestrates that sequence. It is the central coordinator:
//   - Admin declares a member default → member is immediately suspended
//   - Admin calls each stage in order; the contract enforces sequencing
//   - At each stage the recovered amount is tracked; if the shortfall is
//     covered the waterfall stops (no unnecessary draws on later stages)
//   - The resolved flag is set when the full shortfall is covered or
//     all stages are exhausted
//
// Deployment note: this contract must be set as an authorized caller on both
// MarginManager and GuarantyPool (call authorize(address(this)) on each after
// deployment) so it can invoke their restricted functions.
//
// On ARC: requires explicit design and deployment. Not auto-replaced by the
// base ERC-8183 implementation. Must be wired in as part of Phase 4–5 of
// the adoption strategy.

interface IMarginManager {
    function declareBreach(address participant) external returns (uint256 liquidated);
    function totalMargin(address participant) external view returns (uint256);
}

interface IGuarantyPool {
    function deployFunds(address defaultedMember, uint256 amount) external;
    function issueAssessment(uint256 totalShortfall) external;
    function suspendMember(address member) external;
    function poolAvailable() external view returns (uint256);
}

contract DefaultWaterfall {
    enum WaterfallStage { None, OwnMargin, GuarantyPool, Assessment, Resolved }

    struct DefaultEvent {
        address        defaultedMember;
        uint256        totalShortfall;  // original loss to be covered
        uint256        recovered;       // running total recovered through waterfall
        WaterfallStage stage;
        uint256        declaredAt;
        bool           resolved;
    }

    IMarginManager public immutable marginManager;
    IGuarantyPool  public immutable guarantyPool;
    address        public admin;

    uint256 public nextDefaultId;
    mapping(uint256 => DefaultEvent) public defaults;

    event DefaultDeclared(uint256 indexed defaultId, address indexed member, uint256 shortfall);
    event StageExecuted(uint256 indexed defaultId, WaterfallStage stage, uint256 recovered, uint256 remaining);
    event DefaultResolved(uint256 indexed defaultId, uint256 totalRecovered, bool fullyCovered);

    modifier onlyAdmin() {
        require(msg.sender == admin, "admin only");
        _;
    }

    // Deploy after MarginManager and GuarantyPool, then call authorize() on each.
    constructor(address _marginManager, address _guarantyPool) {
        marginManager = IMarginManager(_marginManager);
        guarantyPool  = IGuarantyPool(_guarantyPool);
        admin         = msg.sender;
    }

    // Admin declares a member default. Suspends the member immediately and
    // opens the waterfall at Stage 1. The shortfall is the total loss that
    // must be absorbed (e.g. the notional of unsettled positions).
    function declareDefault(address member, uint256 shortfall)
        external
        onlyAdmin
        returns (uint256 defaultId)
    {
        require(shortfall > 0, "zero shortfall");
        guarantyPool.suspendMember(member);

        defaultId = nextDefaultId++;
        defaults[defaultId] = DefaultEvent({
            defaultedMember: member,
            totalShortfall:  shortfall,
            recovered:       0,
            stage:           WaterfallStage.OwnMargin,
            declaredAt:      block.timestamp,
            resolved:        false
        });

        emit DefaultDeclared(defaultId, member, shortfall);
    }

    // Stage 1: Liquidate the defaulted member's own posted margin.
    // MarginManager.declareBreach returns the amount liquidated; it stays
    // in MarginManager until the exchange sweeps it to cover the shortfall.
    function executeOwnMarginStage(uint256 defaultId) external onlyAdmin {
        DefaultEvent storage d = defaults[defaultId];
        require(!d.resolved, "already resolved");
        require(d.stage == WaterfallStage.OwnMargin, "wrong stage");

        uint256 liquidated = marginManager.declareBreach(d.defaultedMember);
        d.recovered += liquidated;

        emit StageExecuted(defaultId, WaterfallStage.OwnMargin, liquidated, _remaining(d));

        if (d.recovered >= d.totalShortfall) {
            _resolve(d, defaultId);
        } else {
            d.stage = WaterfallStage.GuarantyPool;
        }
    }

    // Stage 2: Draw from the shared guaranty pool for the remaining shortfall.
    // Draws only what is needed (not the whole pool) to preserve it for other
    // potential defaults.
    function executeGuarantyPoolStage(uint256 defaultId) external onlyAdmin {
        DefaultEvent storage d = defaults[defaultId];
        require(!d.resolved, "already resolved");
        require(d.stage == WaterfallStage.GuarantyPool, "wrong stage");

        uint256 remaining = _remaining(d);
        uint256 available = guarantyPool.poolAvailable();
        uint256 toDeploy  = remaining < available ? remaining : available;

        if (toDeploy > 0) {
            guarantyPool.deployFunds(d.defaultedMember, toDeploy);
            d.recovered += toDeploy;
        }

        emit StageExecuted(defaultId, WaterfallStage.GuarantyPool, toDeploy, _remaining(d));

        if (d.recovered >= d.totalShortfall) {
            _resolve(d, defaultId);
        } else {
            d.stage = WaterfallStage.Assessment;
        }
    }

    // Stage 3: Issue a pro-rata assessment to surviving members for any shortfall
    // not covered by Stages 1–2. Assessment amounts are emitted as events;
    // members must call GuarantyPool.postContribution to meet them.
    // This is the final stage — waterfall is marked resolved regardless, as
    // the assessment legally obligates surviving members to contribute.
    function executeAssessmentStage(uint256 defaultId) external onlyAdmin {
        DefaultEvent storage d = defaults[defaultId];
        require(!d.resolved, "already resolved");
        require(d.stage == WaterfallStage.Assessment, "wrong stage");

        uint256 remaining = _remaining(d);
        guarantyPool.issueAssessment(remaining);

        emit StageExecuted(defaultId, WaterfallStage.Assessment, remaining, 0);
        _resolve(d, defaultId);
    }

    function remainingShortfall(uint256 defaultId) external view returns (uint256) {
        return _remaining(defaults[defaultId]);
    }

    function _remaining(DefaultEvent storage d) internal view returns (uint256) {
        return d.totalShortfall > d.recovered ? d.totalShortfall - d.recovered : 0;
    }

    function _resolve(DefaultEvent storage d, uint256 defaultId) internal {
        d.stage    = WaterfallStage.Resolved;
        d.resolved = true;
        emit DefaultResolved(defaultId, d.recovered, d.recovered >= d.totalShortfall);
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        admin = newAdmin;
    }
}
