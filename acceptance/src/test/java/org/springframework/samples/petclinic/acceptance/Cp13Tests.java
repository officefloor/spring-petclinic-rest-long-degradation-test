package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp13 namesake-count: Return 'namesakeCount' = the number of existing owners (before this create) sharing the sa... */
@Tag("cp13")
class Cp13Tests extends AcceptanceBase {

	@Test
	void coreCountsNamesakes() throws Exception {
		ObjectNode a = ownerNode();
		a.put("firstName", "Ann"); a.put("lastName", "namesake");
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("firstName", "Ann"); b.put("lastName", "namesake");
		int id = createOwnerOk(b);
		getOwner(id).andExpect(jsonPath("$.namesakeCount").value(1));
	}
}
