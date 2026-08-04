package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cp57 welcome-notify: On successful create, enqueue a welcome notification: emit via the logger named NOTIFY a l... */
@Tag("cp57")
class Cp57Tests extends AcceptanceBase {

	@Test
	void coreEnqueuesWelcome() throws Exception {
		try (AuditLogCapture notify = new AuditLogCapture("NOTIFY")) {
			int id = createOwnerOk(structuredOwner());
			assertTrue(notify.anyContains(String.valueOf(id))); // TODO: also memberId
		}
	}
}
