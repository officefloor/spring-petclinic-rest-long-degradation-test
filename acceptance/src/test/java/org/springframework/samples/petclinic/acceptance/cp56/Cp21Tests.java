package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** cp21 audit-create, UPDATED by cp56: customerCode is gone from the audit line; it still carries the
 *  owner id and registrationDate (stable identifiers). */
@Tag("cp21")
class Cp21Tests extends AcceptanceBase {

	@Test
	void coreAuditLineHasIdAndDate() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(knownOwner("Sydney"));
			JsonNode r = fetchOwner(id);
			assertTrue(audit.anyContains(String.valueOf(id), r.get("registrationDate").asText()));
		}
	}
}
