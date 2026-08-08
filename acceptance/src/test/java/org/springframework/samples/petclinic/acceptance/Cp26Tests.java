package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** telephone-country-length: Validate the E.164 telephone's national-number length against its country code ('+61' requ... */
@Tag("cp26")
class Cp26Tests extends AcceptanceBase {

	@Test
	void errorRejectsWrongNationalLength() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "+61 123");
		createOwner(o).andExpect(status().isBadRequest()); // +61 needs 9 national digits
	}
}
