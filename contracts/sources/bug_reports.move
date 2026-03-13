/// On-chain bug report registry for MONOLITH anomaly detection.
///
/// Authorized reporters (AdminCap holders) file bug reports that emit
/// `BugReportFiled` events for permanent on-chain attestation.
module monolith_bug_reports::bug_reports {
    use sui::event;

    // ===== Error Constants =====

    const EInvalidSeverity: u64 = 0;
    const EEmptyAnomalyType: u64 = 1;
    const EEmptyAnomalyHash: u64 = 2;

    // ===== Types =====

    /// Capability granting permission to file bug reports.
    /// Never placed in shared objects — transferred to authorized reporters.
    public struct AdminCap has key, store {
        id: UID,
    }

    /// Shared registry tracking total reports and the next report ID.
    public struct BugReportRegistry has key {
        id: UID,
        total_reports: u64,
        next_report_id: u64,
    }

    /// Event emitted when a bug report is filed on-chain.
    public struct BugReportFiled has copy, drop {
        report_id: u64,
        anomaly_type: vector<u8>,
        severity: u8,
        anomaly_hash: vector<u8>,
        reporter: address,
        timestamp_ms: u64,
    }

    // ===== Init =====

    /// Module initializer: creates the shared registry and transfers
    /// an AdminCap to the deployer.
    fun init(ctx: &mut TxContext) {
        let registry = BugReportRegistry {
            id: object::new(ctx),
            total_reports: 0,
            next_report_id: 1,
        };
        transfer::share_object(registry);

        let admin_cap = AdminCap {
            id: object::new(ctx),
        };
        transfer::transfer(admin_cap, ctx.sender());
    }

    // ===== Public Entry Functions =====

    /// File a bug report. Requires AdminCap for authorization.
    /// Severity: 1=low, 2=medium, 3=high, 4=critical.
    public entry fun file_report(
        _cap: &AdminCap,
        registry: &mut BugReportRegistry,
        anomaly_type: vector<u8>,
        severity: u8,
        anomaly_hash: vector<u8>,
        timestamp_ms: u64,
        ctx: &mut TxContext,
    ) {
        // Validate inputs
        assert!(severity >= 1 && severity <= 4, EInvalidSeverity);
        assert!(!anomaly_type.is_empty(), EEmptyAnomalyType);
        assert!(!anomaly_hash.is_empty(), EEmptyAnomalyHash);

        let report_id = registry.next_report_id;
        registry.next_report_id = report_id + 1;
        registry.total_reports = registry.total_reports + 1;

        event::emit(BugReportFiled {
            report_id,
            anomaly_type,
            severity,
            anomaly_hash,
            reporter: ctx.sender(),
            timestamp_ms,
        });
    }

    /// Grant another address an AdminCap (only existing admin can do this).
    public entry fun grant_admin(
        _cap: &AdminCap,
        recipient: address,
        ctx: &mut TxContext,
    ) {
        let new_cap = AdminCap {
            id: object::new(ctx),
        };
        transfer::transfer(new_cap, recipient);
    }

    // ===== Accessors =====

    /// Get the total number of reports filed.
    public fun get_total_reports(registry: &BugReportRegistry): u64 {
        registry.total_reports
    }

    /// Get the next report ID that will be assigned.
    public fun get_next_report_id(registry: &BugReportRegistry): u64 {
        registry.next_report_id
    }

    // ===== Test Helpers =====

    #[test_only]
    public fun init_for_testing(ctx: &mut TxContext) {
        init(ctx);
    }
}
