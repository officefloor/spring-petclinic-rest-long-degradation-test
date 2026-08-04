package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cp53 audit-event: In addition to the audit line, emit an immutable structured event via AUDIT: a JSON object... */
@Tag("cp53")
class Cp53Tests extends AcceptanceBase {

	@Test
	void coreEmitsSequencedEvent() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			createOwnerOk(structuredOwner());
			assertTrue(audit.anyContains("OWNER_CREATED")); // TODO: assert monotonically increasing seq
		}
	}
}
