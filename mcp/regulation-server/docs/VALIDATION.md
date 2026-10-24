# Kết quả kiểm tra gói bàn giao

Môi trường: Linux / Python 3.12.14. SDK MCP 2.3.0.

15 kiểm thử thành phần đạt; MCP stdio subprocess đạt; Ruff đạt. Chưa xác nhận trên Windows nhận bàn giao hoặc Agent thật của nhóm.

```text
test_amendment_both_directions (test_handoff.HandoffTests.test_amendment_both_directions) ... ok
test_certificate_reference (test_handoff.HandoffTests.test_certificate_reference) ... ok
test_citations_and_raw_text (test_handoff.HandoffTests.test_citations_and_raw_text) ... ok
test_context_is_not_approval (test_handoff.HandoffTests.test_context_is_not_approval) ... ok
test_default_denies (test_handoff.HandoffTests.test_default_denies) ... ok
test_handbook_and_faq_indexed (test_handoff.HandoffTests.test_handbook_and_faq_indexed) ... ok
test_invalid_arguments (test_handoff.HandoffTests.test_invalid_arguments) ... ok
test_missing_provision (test_handoff.HandoffTests.test_missing_provision) ... ok
test_multihop_replacement (test_handoff.HandoffTests.test_multihop_replacement) ... ok
test_negative_weather (test_handoff.HandoffTests.test_negative_weather) ... ok
test_repeal_has_source (test_handoff.HandoffTests.test_repeal_has_source) ... ok
test_schema_closed (test_handoff.HandoffTests.test_schema_closed) ... ok
test_thesis_with_language_and_registration (test_handoff.HandoffTests.test_thesis_with_language_and_registration) ... ok
test_unknown_tool (test_handoff.HandoffTests.test_unknown_tool) ... ok
test_zero_hops (test_handoff.HandoffTests.test_zero_hops) ... ok

----------------------------------------------------------------------
Ran 15 tests in 0.159s

OK

```

```text
PASS initialize draft
PASS list_tools and schemas
PASS search + graph reference
PASS get_provision citation
PASS version expansion through MCP
PASS error envelope NOT_FOUND
PASS error envelope INVALID_ARGUMENT
PASS error envelope INVALID_ARGUMENT
PASS initialize default
PASS list_tools and schemas
PASS default draft denial
ALL MCP STDIO CHECKS PASSED

```

```text
All checks passed!

```

