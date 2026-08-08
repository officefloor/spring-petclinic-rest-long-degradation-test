package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** audit-enriched: the create AUDIT line must also carry membershipLevel and membershipNumber
 * (the fields it already logged remain). */
@Tag("cp43")
class Cp43Tests extends AcceptanceBase {

	@Test
	void coreAuditIncludesLevelAndNumber() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			ObjectNode o = withPostcode(ownerNode());
			o.put("email", uniqueEmail());
			int id = createOwnerOk(o);
			JsonNode r = fetchOwner(id);
			assertTrue(audit.anyContains(r.get("membershipNumber").asText(),
					String.valueOf(r.get("membershipLevel").asInt())));
		}
	}
}
