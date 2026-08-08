package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** identity-key: the identityKey is now a 64-hex SHA-256 (over
 * telephone|lowerEmail|soundex(lastName)); a repeated full identity still collides with 409. */
@Tag("cp28")
class Cp28Tests extends AcceptanceBase {

	@Test
	void coreIdentityKeyIsSha256Hex() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(structuredOwner()));
		assertTrue(r.get("identityKey").asText().matches("[0-9a-f]{64}"), r.get("identityKey").asText());
	}

	@Test
	void coreRejectsDuplicateIdentity() throws Exception {
		ObjectNode a = structuredOwner();
		a.put("email", uniqueEmail());
		createOwnerOk(a);
		ObjectNode b = a.deepCopy();
		createOwner(b).andExpect(status().isConflict());
	}
}
