package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp06: derived displayName = "LastName, FirstName". */
@Tag("cp06")
class Cp06Tests extends AcceptanceBase {

	@Test
	void coreDisplayName() throws Exception {
		ObjectNode o = ownerNode();
		o.put("firstName", "John");
		String last = o.get("lastName").asText();
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.displayName").value(last + ", John"));
	}
}
