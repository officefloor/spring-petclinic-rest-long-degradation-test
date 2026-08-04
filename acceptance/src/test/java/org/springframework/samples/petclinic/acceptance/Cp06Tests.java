package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp06 initials: Return 'initials' as the upper-cased first letters of firstName and lastName, dot-separate... */
@Tag("cp06")
class Cp06Tests extends AcceptanceBase {

	@Test
	void coreComputesInitials() throws Exception {
		ObjectNode o = ownerNode();
		o.put("firstName", "john"); o.put("lastName", "smith");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.initials").value("J.S."));
	}
}
