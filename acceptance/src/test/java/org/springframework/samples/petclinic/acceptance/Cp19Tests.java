package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/** cp19: every owner creation logs the user + owner id to the AUDIT logger. */
@Tag("cp19")
class Cp19Tests extends AcceptanceBase {

	@Test
	void coreAuditsOwnerCreation() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(ownerNode());
			assertTrue(audit.anyContains("acceptance-admin", String.valueOf(id)),
					"audit should record the user and the new owner id; got " + audit.messages());
		}
	}
}
