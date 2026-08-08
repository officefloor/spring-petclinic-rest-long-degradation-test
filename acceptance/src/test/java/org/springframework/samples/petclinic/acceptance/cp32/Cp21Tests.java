package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** audit-create: the audit line carries the new region-and-hash customerCode,
 * alongside the owner id and registrationDate. */
@Tag("cp21")
class Cp21Tests extends AcceptanceBase {

	@Test
	void coreAuditLineHasRegionHashCode() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(knownOwner("Sydney"));
			JsonNode r = fetchOwner(id);
			assertTrue(audit.anyContains(String.valueOf(id),
					r.get("customerCode").asText(), r.get("registrationDate").asText()));
		}
	}
}
