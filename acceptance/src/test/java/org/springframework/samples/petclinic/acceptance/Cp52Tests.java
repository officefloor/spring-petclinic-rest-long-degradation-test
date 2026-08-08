package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** identity-key-v2: identityKey = SHA-256 hex over (normalizedTelephone | lowerEmail |
 * soundex(lastName)); duplicate detection (409) uses it. The exact key depends on soundex, so the
 * deterministic oracle is the collision (identical identity -> 409) plus the exact 64-hex shape. */
@Tag("cp52")
class Cp52Tests extends AcceptanceBase {

	@Test
	void coreIdentityKeyIsSha256Hex() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(structuredOwner()));
		String key = r.get("identityKey").asText();
		assertTrue(key.matches("[0-9a-f]{64}"), key);
	}

	@Test
	void coreRejectsDuplicateIdentity() throws Exception {
		ObjectNode a = structuredOwner();
		a.put("email", uniqueEmail());
		createOwnerOk(a);
		ObjectNode b = a.deepCopy(); // identical telephone / email / lastName -> same v2 key
		createOwner(b).andExpect(status().isConflict());
	}
}
