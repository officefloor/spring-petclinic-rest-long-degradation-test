package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** audit-event: customerCode is unified into memberId, so the structured event
 * must now carry the memberId as the owner's primary identifier (there is no customerCode to log).
 * Verifies the event switched identifiers rather than logging a stale/removed field. */
@Tag("cp53")
class Cp53Tests extends AcceptanceBase {

	@Test
	void coreEventCarriesMemberId() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(knownOwner("Sydney"));
			JsonNode r = fetchOwner(id);
			assertTrue(audit.anyContains("OWNER_CREATED", String.valueOf(id),
					r.get("memberId").asText()));
		}
	}
}
