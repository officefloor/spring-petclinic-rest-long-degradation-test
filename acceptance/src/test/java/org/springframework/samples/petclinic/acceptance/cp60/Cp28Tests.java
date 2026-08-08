package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** identity-key: the identityKey (rederived v2) lives under the nested
 * 'identity' object and is still a 64-hex SHA-256. */
@Tag("cp28")
class Cp28Tests extends AcceptanceBase {

	@Test
	void coreIdentityKeyUnderIdentity() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(structuredOwner()));
		String key = r.get("identity").get("identityKey").asText();
		assertTrue(key.matches("[0-9a-f]{64}"), key);
	}
}
