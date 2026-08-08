package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** cp53 audit-event: besides the audit line, emit a structured event via AUDIT
 *  {seq, ownerId, customerCode, membershipLevel, event:'OWNER_CREATED'}. The event must carry the
 *  owner id AND the current primary identifier (customerCode here); asserting the identifier is what
 *  lets later checkpoints prove the event switched to the memberId. */
@Tag("cp53")
class Cp53Tests extends AcceptanceBase {

	@Test
	void coreEventCarriesIdAndIdentifier() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(knownOwner("Sydney"));
			JsonNode r = fetchOwner(id);
			// one AUDIT event line must contain the marker, the owner id and the customerCode
			assertTrue(audit.anyContains("OWNER_CREATED", String.valueOf(id),
					r.get("customerCode").asText()));
		}
	}
}
