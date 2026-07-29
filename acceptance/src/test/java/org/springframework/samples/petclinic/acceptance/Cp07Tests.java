package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp07: derived initials = first letters of first + last name, e.g. "J.D.". */
@Tag("cp07")
class Cp07Tests extends AcceptanceBase {

	@Test
	void coreInitials() throws Exception {
		ObjectNode o = ownerNode();
		o.put("firstName", "John");   // ownerNode's letters-only lastName starts with "S"
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.initials").value("J.S."));
	}
}
