package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp10: AUDIT log entry on owner update, listing changed fields. */
@Tag("cp10")
class Cp10Tests extends AcceptanceBase {

	@Test
	void coreLogsAuditOnUpdate() throws Exception {
		int id = createOwnerOk(validOwner("Bob", "Jones"));
		try (AuditLogCapture audit = new AuditLogCapture()) {
			ObjectNode upd = validOwner("Bob", "Jones");
			upd.put("city", "Bristol");
			updateOwner(id, upd).andExpect(status().is2xxSuccessful());
			assertTrue(audit.count() > 0, "expected an AUDIT entry on update; got none");
		}
	}

	@Test
	void functionalityAuditMentionsChangedField() throws Exception {
		int id = createOwnerOk(validOwner("Cara", "Lee"));
		try (AuditLogCapture audit = new AuditLogCapture()) {
			ObjectNode upd = validOwner("Cara", "Lee");
			upd.put("city", "Bristol"); // change city
			updateOwner(id, upd).andExpect(status().is2xxSuccessful());
			assertTrue(audit.anyContains("city"),
					"audit should name the changed field 'city'; got " + audit.messages());
		}
	}
}
