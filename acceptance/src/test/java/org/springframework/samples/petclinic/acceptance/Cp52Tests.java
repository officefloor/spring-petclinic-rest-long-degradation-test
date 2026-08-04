package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp52 identity-key-v2: Redesign the identity key: identityKey = SHA-256 hex over (normalizedTelephone + '|' + low... */
@Tag("cp52")
class Cp52Tests extends AcceptanceBase {

	@Test
	void coreIdentityKeyV2Collision() throws Exception {
		ObjectNode a = structuredOwner();
		createOwnerOk(a);
		ObjectNode b = structuredOwner();
		b.put("telephone", a.get("telephone").asText());
		createOwner(b).andExpect(status().isConflict()); // TODO: soundex-based key
	}
}
