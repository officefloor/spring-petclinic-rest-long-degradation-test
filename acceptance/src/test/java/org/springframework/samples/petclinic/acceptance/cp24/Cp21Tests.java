package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** audit-create: the create audit line records the numeric membershipLevel
 * (instead of a tier), alongside the owner id it already logged. */
@Tag("cp21")
class Cp21Tests extends AcceptanceBase {

	@Test
	void coreAuditLineRecordsLevel() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			ObjectNode o = ownerNode();
			o.put("email", uniqueEmail());
			int id = createOwnerOk(o);
			JsonNode r = fetchOwner(id);
			assertTrue(audit.anyContains(String.valueOf(id),
					String.valueOf(r.get("membershipLevel").asInt())));
		}
	}
}
