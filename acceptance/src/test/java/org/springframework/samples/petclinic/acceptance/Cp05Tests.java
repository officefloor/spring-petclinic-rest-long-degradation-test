package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** display-name: When an owner is created, return 'displayName' formatted exactly as 'LastName, FirstName'... */
@Tag("cp05")
class Cp05Tests extends AcceptanceBase {

	@Test
	void coreComputesDisplayName() throws Exception {
		ObjectNode o = ownerNode();
		o.put("firstName", "John");
		String last = o.get("lastName").asText();
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.displayName").value(last + ", John"));
	}
}
