// Non-consequential tools: reading, looking up, flagging, and opening a human review.
//
// Note what has no action at all here, and therefore no permit anywhere in this
// directory: changing a vendor's bank details. Deny-by-default makes that impossible for
// any agent to attempt, rather than merely difficult.

@id("read-tools-allowed")
permit(
  principal,
  action in [
    Action::"read_inbox",
    Action::"extract_fields",
    Action::"lookup_vendor",
    Action::"check_duplicate",
    Action::"flag_for_review",
    Action::"open_bank_change_review",
    Action::"export_vendor_master"
  ],
  resource
);
