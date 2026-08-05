package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp10 household-duplicate, UPDATED by cp28: the household duplicate check is expressed through the
 *  identityKey. Same lastName + address (same household, same telephone) still rejects with 409. */
@Tag("cp10")
class Cp10Tests extends AcceptanceBase {

	@Test
	void coreHouseholdDuplicateRejected() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", a.get("lastName").asText());
		b.put("address", a.get("address").asText());
		b.put("telephone", a.get("telephone").asText());
		createOwner(b).andExpect(status().isConflict());
	}
}
