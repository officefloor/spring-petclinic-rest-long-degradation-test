package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp29 postcode: The request must include 'postcode' (4 digits) that belongs to the owner's city per a city... */
@Tag("cp29")
class Cp29Tests extends AcceptanceBase {

	@Test
	void errorRejectsMismatchedPostcode() throws Exception {
		ObjectNode o = ownerNode();
		o.put("postcode", "9999");
		createOwner(o).andExpect(status().isBadRequest()); // TODO: postcode not valid for city
	}
}
