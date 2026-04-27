// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// CCP Function 4: Risk Mutualization (Guaranty Pool)
//
// NSCC's Clearing Fund mutualizes loss across all clearing members. When a
// member's margin is exhausted after a default, the CCP draws from this shared
// pool before assessing surviving members. The pool is funded by required
// contributions sized to each member's trading volume and risk profile.
//
// This contract is the on-chain equivalent of NSCC's Clearing Fund:
//   - Members post required contributions at onboarding
//   - Admin deploys funds to cover shortfalls after Stage 1 (own margin) is exhausted
//   - If the pool itself is exhausted, admin issues a pro-rata assessment to
//     surviving members — they must post additional contributions to replenish
//   - Suspended (defaulted) members are excluded from assessments
//
// On ARC: requires explicit deployment. DefaultWaterfall must be authorized
// to call deployFunds, issueAssessment, and suspendMember.

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

contract GuarantyPool {
    struct Member {
        uint256 required;   // minimum contribution (admin-set per risk profile)
        uint256 posted;     // actual amount posted to pool
        bool    suspended;  // true if member has defaulted
    }

    IERC20  public immutable usdc;
    address public admin;

    mapping(address => Member) public members;
    mapping(address => bool)   public authorized; // e.g. DefaultWaterfall
    address[]                  public memberList;

    uint256 public totalPool;
    uint256 public deployedAmount; // cumulative funds drawn for defaults

    event MemberAdded(address indexed member, uint256 requiredContribution);
    event ContributionPosted(address indexed member, uint256 amount, uint256 poolTotal);
    event FundsDeployed(address indexed defaultedMember, uint256 amount, uint256 poolRemaining);
    event AssessmentIssued(address indexed member, uint256 assessedAmount);
    event MemberSuspended(address indexed member);
    event ExcessWithdrawn(address indexed member, uint256 amount);

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

    // Admin adds a clearing member and sets their minimum required contribution.
    // Required contribution is sized to the member's trading volume and risk profile,
    // mirroring NSCC's monthly recalibration of clearing fund requirements.
    function addMember(address member, uint256 requiredContribution) external onlyAdmin {
        require(members[member].required == 0, "already a member");
        require(requiredContribution > 0, "contribution required");
        members[member].required = requiredContribution;
        memberList.push(member);
        emit MemberAdded(member, requiredContribution);
    }

    // Members post their required (or additional) contribution to the shared pool.
    function postContribution(uint256 amount) external {
        Member storage m = members[msg.sender];
        require(m.required > 0, "not a member");
        require(!m.suspended, "member suspended");

        usdc.transferFrom(msg.sender, address(this), amount);
        m.posted  += amount;
        totalPool += amount;
        emit ContributionPosted(msg.sender, amount, totalPool);
    }

    // Admin (or DefaultWaterfall) deploys pool funds to cover a default shortfall
    // after the defaulted member's own margin has been exhausted (Stage 2 waterfall).
    function deployFunds(address defaultedMember, uint256 amount) external onlyAdminOrAuthorized {
        require(amount <= poolAvailable(), "insufficient pool");
        deployedAmount += amount;
        usdc.transfer(defaultedMember, amount);
        emit FundsDeployed(defaultedMember, amount, poolAvailable());
    }

    // Admin issues a pro-rata assessment to surviving members when the pool is
    // insufficient to cover the full shortfall (Stage 3 waterfall). Assessment
    // amounts are emitted for each member; actual collection is a separate
    // postContribution call by each member.
    function issueAssessment(uint256 totalShortfall) external onlyAdminOrAuthorized {
        uint256 survivingPool;
        for (uint256 i = 0; i < memberList.length; i++) {
            address m = memberList[i];
            if (!members[m].suspended) survivingPool += members[m].posted;
        }
        require(survivingPool > 0, "no surviving members");

        for (uint256 i = 0; i < memberList.length; i++) {
            address m = memberList[i];
            if (members[m].suspended) continue;
            // Pro-rata share of the shortfall proportional to each member's posted contribution.
            uint256 share = (totalShortfall * members[m].posted) / survivingPool;
            if (share > 0) emit AssessmentIssued(m, share);
        }
    }

    // Admin or DefaultWaterfall suspends a defaulted member immediately on default
    // declaration. Suspended members cannot post further trades and are excluded
    // from assessments.
    function suspendMember(address member) external onlyAdminOrAuthorized {
        require(members[member].required > 0, "not a member");
        members[member].suspended = true;
        emit MemberSuspended(member);
    }

    // Members withdraw posted amount above their required minimum, provided
    // they are in good standing.
    function withdrawExcess() external {
        Member storage m = members[msg.sender];
        require(m.required > 0, "not a member");
        require(!m.suspended, "suspended");

        uint256 excess = m.posted > m.required ? m.posted - m.required : 0;
        require(excess > 0, "no excess");

        m.posted  -= excess;
        totalPool -= excess;
        usdc.transfer(msg.sender, excess);
        emit ExcessWithdrawn(msg.sender, excess);
    }

    function poolAvailable() public view returns (uint256) {
        return totalPool > deployedAmount ? totalPool - deployedAmount : 0;
    }

    function isMemberInGoodStanding(address member) external view returns (bool) {
        Member storage m = members[member];
        return m.required > 0 && !m.suspended && m.posted >= m.required;
    }

    function getMemberList() external view returns (address[] memory) {
        return memberList;
    }

    function authorize(address caller) external onlyAdmin {
        authorized[caller] = true;
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        admin = newAdmin;
    }
}
