package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** no-future-date: Reject a supplied registrationDate later than the server date. Respond with 400.... */
@Tag("cp33")
class Cp33Tests extends AcceptanceBase {

	@Test
	void errorRejectsFutureDate() throws Exception {
		ObjectNode o = ownerNode();
		o.put("registrationDate", "2999-01-01");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
