package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** cp43 audit-enriched, UPDATED by cp56: membershipNumber is gone, so the audit line now records the
 *  owner id and the membershipLevel. */
@Tag("cp43")
class Cp43Tests extends AcceptanceBase {

	@Test
	void coreAuditLineHasLevel() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			ObjectNode o = knownOwner("Sydney");
			o.put("email", uniqueEmail());
			int id = createOwnerOk(o);
			JsonNode r = fetchOwner(id);
			assertTrue(audit.anyContains(String.valueOf(id),
					String.valueOf(r.get("membershipLevel").asInt())));
		}
	}
}
