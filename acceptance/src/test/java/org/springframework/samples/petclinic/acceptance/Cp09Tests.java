package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp09: AUDIT log entry on owner create (user + owner id). */
@Tag("cp09")
class Cp09Tests extends AcceptanceBase {

	@Test
	void coreLogsAuditOnCreate() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(validOwner());
			assertTrue(audit.anyContains(String.valueOf(id)),
					"expected an AUDIT entry mentioning owner id " + id + "; got " + audit.messages());
		}
	}

	@Test
	void functionalityDoesNotLogAuditOnRejectedCreate() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			ObjectNode bad = validOwner();
			bad.put("telephone", "");
			createOwner(bad).andExpect(status().isBadRequest());
			assertEquals(0, audit.count(), "no AUDIT entry expected for a rejected create");
		}
	}
}
