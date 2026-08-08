package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** welcome-notify: on successful create, a NOTIFY log line carries the owner id and the
 * memberId. */
@Tag("cp57")
class Cp57Tests extends AcceptanceBase {

	@Test
	void coreEnqueuesWelcome() throws Exception {
		try (AuditLogCapture notify = new AuditLogCapture("NOTIFY")) {
			int id = createOwnerOk(structuredOwner());
			String memberId = fetchOwner(id).get("memberId").asText();
			assertTrue(notify.anyContains(String.valueOf(id), memberId));
		}
	}
}
