// Payment policies.
//
// The forbid on the destination account has no humanApproved escape hatch, and that is
// deliberate: an approver looking at a convincing email is exactly the person an attacker
// is trying to fool. Money can only go to the account already on file.

@id("pay-permit-within-mandate")
permit(principal, action == Action::"pay_vendor", resource)
when {
  context.mandate.allowedActions.contains("pay_vendor") &&
  resource.status == "ACTIVE" &&
  context.amountPaise <= context.mandate.maxAmountPaise
};

@id("pay-account-must-be-master")
forbid(principal, action == Action::"pay_vendor", resource)
unless { context.account.trusted && context.accountMatchesVendorMaster };

@id("pay-vendor-match-required")
forbid(principal, action == Action::"pay_vendor", resource)
unless { context.vendorMatchVerified || context.humanApproved };

@id("pay-no-duplicates")
forbid(principal, action == Action::"pay_vendor", resource)
when { context.isDuplicateInvoice };

@id("pay-above-auto-limit-needs-human")
forbid(principal, action == Action::"pay_vendor", resource)
when { context.amountPaise > context.mandate.autoApproveLimitPaise }
unless { context.humanApproved };
