package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cp21 audit-create: On successful create, emit an audit line via the logger named AUDIT containing the owner i... */
@Tag("cp21")
class Cp21Tests extends AcceptanceBase {

	@Test
	void coreLogsAuditOnCreate() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(ownerNode());
			assertTrue(audit.anyContains(String.valueOf(id))); // TODO: also customerCode + registrationDate
		}
	}
}
