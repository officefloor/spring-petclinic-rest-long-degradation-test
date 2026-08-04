package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp28 identity-key: Consolidate all duplicate detection into a single derived 'identityKey' = normalizedTeleph... */
@Tag("cp28")
class Cp28Tests extends AcceptanceBase {

	@Test
	void coreRejectsIdentityCollision() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("telephone", a.get("telephone").asText());
		createOwner(b).andExpect(status().isConflict()); // same identityKey
	}
}
