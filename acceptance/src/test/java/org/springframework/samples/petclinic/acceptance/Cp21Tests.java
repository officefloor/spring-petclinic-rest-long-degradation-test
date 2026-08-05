package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** cp21 audit-create: on successful create, an AUDIT log line carries the owner id, the
 *  customerCode and the registrationDate. */
@Tag("cp21")
class Cp21Tests extends AcceptanceBase {

	@Test
	void coreLogsAuditOnCreate() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(ownerNode());
			JsonNode o = fetchOwner(id);
			assertTrue(audit.anyContains(String.valueOf(id),
					o.get("customerCode").asText(), o.get("registrationDate").asText()));
		}
	}
}
