package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** welcome-notify: the NOTIFY line still carries the owner id and the memberId,
 * which is now read from the nested 'identity' object. */
@Tag("cp57")
class Cp57Tests extends AcceptanceBase {

	@Test
	void coreNotifyHasIdAndMemberId() throws Exception {
		try (AuditLogCapture notify = new AuditLogCapture("NOTIFY")) {
			int id = createOwnerOk(knownOwner("Sydney"));
			String memberId = fetchOwner(id).get("identity").get("memberId").asText();
			assertTrue(notify.anyContains(String.valueOf(id), memberId));
		}
	}
}
