package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cp53 audit-event: besides the audit line, emit a structured event via AUDIT
 *  {seq, ownerId, customerCode, membershipLevel, event:'OWNER_CREATED'}. Assert the event marker and
 *  the owner id appear on the AUDIT logger. */
@Tag("cp53")
class Cp53Tests extends AcceptanceBase {

	@Test
	void coreEmitsCreatedEvent() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(structuredOwner());
			assertTrue(audit.anyContains("OWNER_CREATED", String.valueOf(id)));
		}
	}
}
