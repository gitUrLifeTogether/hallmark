// Outbound email policies.
//
// Confidential material stays inside the company, with no approval override, so an
// "auditor" address that arrived inside an attachment cannot become a destination for
// the vendor master.

@id("email-permit-within-mandate")
permit(principal, action == Action::"send_email", resource)
when { context.mandate.allowedActions.contains("send_email") };

@id("email-recipient-must-be-trusted")
forbid(principal, action == Action::"send_email", resource)
unless {
  context.recipient.trusted ||
  context.recipientIsKnownContact ||
  context.recipientIsInternal
};

@id("email-confidential-internal-only")
forbid(principal, action == Action::"send_email", resource)
when { context.bodyConfidentiality == "CONFIDENTIAL" && !context.recipientIsInternal };
